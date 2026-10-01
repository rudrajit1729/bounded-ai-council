#!/usr/bin/env python3
"""
Model driver: every model call of the pipeline goes through `call()`, every decision-model call
through `decide()`.

Each call is stateless. The driver builds one prompt from a brief and the files that role may
see (its input manifest), sends it to a process or endpoint with no file or tool access, and
saves the JSON that comes back to the paths the brief names. Every call is appended to
<workspace>/logs/calls.jsonl with the model id that answered, the reasoning setting, token usage
as the vendor reports it, wall time, and the sha256 of each input and output.

Backends (set per model family in config.yaml, `models.<family>.backend`):

  claude_cli     `claude -p` with no tools and no MCP servers; usage from --output-format json
  codex_cli      `codex exec` in a read-only sandbox and an empty working directory
  anthropic_api  the official `anthropic` Python SDK (pip install anthropic); key from the
                 environment variable named in `api_key_env` (default ANTHROPIC_API_KEY)
  openai_api     an OpenAI-compatible /chat/completions endpoint over HTTPS (base_url configurable)
  gemini_api     the Gemini generateContent endpoint over HTTPS (key in a header, not the URL)
  command        any program: the prompt on stdin, the reply on stdout
  manual         writes the prompt to <workspace>/manual/<call>.prompt.md and waits for
                 <call>.reply.json; used when an agent or a person answers the prompts
  replay         reads <replay_dir>/<call>.reply.json, recorded earlier from a manual run
                 (`council.py export-replies`); no model is contacted. Used by the offline demo.

The decision model (`decide()`) has the same choice: `typesafe` (the default), `command`, `manual`
(the request is written to <workspace>/manual/<call>.prompt.md) and `replay`.

Token counts of manual and replay calls are estimated from characters (about 4 per token) and
flagged `tokens_estimated` in the log; every other backend logs what the vendor reports.

Keys are read from environment variables whose NAMES are in the config; no key is ever written
to a file or a log.

Standard library only (plus `anthropic` if that backend is chosen).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CFG = None            # set by configure()
CALL_SUFFIX = ""      # appended to every call id; run.py sets "__v<version>" when a refined codebook recodes the corpus
WS: Path | None = None
LOG: Path | None = None
_lock = threading.Lock()

SYSTEM = ("You are one role in a qualitative analysis procedure. You have no file or tool access: "
          "the files your brief names are included in this message, each under a line "
          "'=== FILE: <path> ==='. Where the brief says to write or return a file, do not write "
          "anything; instead return a single JSON object whose keys are the output paths the "
          "brief names and whose values are those files' contents (a JSON object for .json files, "
          "a list of JSON objects for .jsonl files). Return only that JSON object, with no prose "
          "and no code fences.")
SHORT_SYSTEM = "Follow the brief exactly. Return only JSON."
MAX_OUTPUT_TOKENS = 64000


class ManualPending(Exception):
    """A manual-backend call has no reply yet; the prompt file is waiting to be answered."""


def configure(cfg):
    global CFG, WS, LOG
    CFG = cfg
    WS = cfg.workspace
    LOG = Path(os.environ.get("COUNCIL_CALL_LOG", WS / "logs" / "calls.jsonl"))


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------------- prompt and reply
def build_prompt(brief: Path, inputs: list, instruction: str = "") -> tuple[str, dict]:
    parts = [SYSTEM, "", "=== BRIEF ===", Path(brief).read_text(encoding="utf-8")]
    hashes = {Path(brief).name: sha(Path(brief).read_bytes())}
    for label, path in inputs:
        data = Path(path).read_bytes()
        hashes[label] = sha(data)
        parts += ["", "=== FILE: %s ===" % label, data.decode("utf-8")]
    if instruction:
        parts += ["", "=== INSTRUCTION ===", instruction]
    return "\n".join(parts), hashes


def extract_json(text: str) -> dict:
    """Parse the reply. Tolerates code fences, prose around the JSON, and several top-level
    objects in a row (merged key by key when each looks like a whole output)."""
    t = re.sub(r"```(?:json)?", "", text.strip())
    dec, objs, i = json.JSONDecoder(), [], 0
    while True:
        i = t.find("{", i)
        if i < 0:
            break
        try:
            obj, end = dec.raw_decode(t, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict):
            objs.append(obj)
        i = end
    if not objs:
        raise ValueError("no JSON object in reply")
    if len(objs) == 1:
        return objs[0]
    whole = [o for o in objs if any("/" in k or k.endswith((".json", ".jsonl")) for k in o)
             or {"codes", "groups", "challenges", "answers", "replace"} & set(o)]
    if not whole:
        raise ValueError("several JSON fragments and no whole output")
    merged = {}
    for o in whole:
        merged.update(o)
    return merged


# --------------------------------------------------------------------------- backends
def _env_key(spec: dict, default_env: str) -> str:
    name = spec.get("api_key_env") or default_env
    key = os.environ.get(name)
    if not key:
        raise RuntimeError("environment variable %s is not set (named in config as api_key_env)" % name)
    return key


def _post(url: str, body: dict, headers: dict, timeout: int = 3600) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=dict(headers, **{"Content-Type": "application/json"}))
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return json.loads(f.read())


def run_claude_cli(spec, model, prompt, default_reasoning):
    env = dict(os.environ, CLAUDE_CODE_MAX_OUTPUT_TOKENS=str(spec.get("max_output_tokens", MAX_OUTPUT_TOKENS)))
    if not default_reasoning:
        env["MAX_THINKING_TOKENS"] = "0"
    binary = spec.get("binary") or os.environ.get("CLAUDE_BIN", "claude")
    with tempfile.TemporaryDirectory() as cwd:
        p = subprocess.run([binary, "-p", "--model", model, "--output-format", "json", "--tools", "",
                            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                            "--system-prompt", SHORT_SYSTEM],
                           input=prompt, capture_output=True, text=True, cwd=cwd, env=env, timeout=3600)
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise RuntimeError("claude returned no JSON envelope: %s %s" % (p.stdout[-400:], p.stderr[-400:]))
    if out.get("is_error"):
        raise RuntimeError("claude error: %s" % str(out.get("result", ""))[:400])
    if out.get("stop_reason") == "max_tokens" or (out.get("num_turns") or 1) > 1:
        raise RuntimeError("truncated: stop_reason=%s num_turns=%s" % (out.get("stop_reason"), out.get("num_turns")))
    u = out.get("usage", {})
    usage = {"input_tokens": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0),
             "output_tokens": u.get("output_tokens", 0),
             "model_reported": ",".join((out.get("modelUsage") or {}).keys()),
             "reasoning_setting": "default" if default_reasoning else "thinking off",
             "cost_usd_reported": out.get("total_cost_usd")}
    return out.get("result", ""), usage


def run_codex_cli(spec, model, prompt, default_reasoning):
    effort = spec.get("default_effort", "medium") if default_reasoning else (spec.get("reduced_effort") or CFG.d["reasoning"]["reduced_effort"])
    binary = spec.get("binary") or os.environ.get("CODEX_BIN", "codex")
    with tempfile.TemporaryDirectory() as cwd:
        last = Path(cwd) / "last.txt"
        p = subprocess.run([binary, "exec", "-m", model, "-c", "model_reasoning_effort=%s" % effort,
                            "--sandbox", "read-only", "--skip-git-repo-check", "--json",
                            "--output-last-message", str(last), "-"],
                           input=prompt, capture_output=True, text=True, cwd=cwd, timeout=3600)
        text = last.read_text() if last.exists() else ""
    usage, err = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}, ""
    for line in p.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "turn.completed":
            u = ev.get("usage", {})
            usage = {"input_tokens": u.get("input_tokens", 0), "output_tokens": u.get("output_tokens", 0),
                     "reasoning_tokens": u.get("reasoning_output_tokens", 0), "cached_input_tokens": u.get("cached_input_tokens", 0)}
        if ev.get("type") in ("error", "turn.failed"):
            err += json.dumps(ev)
    if not text:
        raise RuntimeError("codex failed: %s %s" % (err[:400], p.stderr[-400:]))
    usage.update(model_reported=model, reasoning_setting="effort %s" % effort)
    return text, usage


def run_anthropic_api(spec, model, prompt, default_reasoning):
    try:
        import anthropic  # type: ignore
    except ImportError:
        raise RuntimeError("backend anthropic_api needs the official SDK: pip install anthropic")
    client = anthropic.Anthropic(api_key=_env_key(spec, "ANTHROPIC_API_KEY"))
    kwargs = dict(model=model, max_tokens=int(spec.get("max_output_tokens", MAX_OUTPUT_TOKENS)), system=SHORT_SYSTEM,
                  messages=[{"role": "user", "content": prompt}])
    if not default_reasoning:
        # Reduced reasoning: lower effort rather than disabling thinking (current models reject disabled thinking).
        kwargs["output_config"] = {"effort": spec.get("reduced_effort") or CFG.d["reasoning"]["reduced_effort"]}
    with client.messages.stream(**kwargs) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("refusal: %s" % getattr(msg, "stop_details", None))
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("truncated: stop_reason=max_tokens")
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    usage = {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens, "model_reported": msg.model,
             "reasoning_setting": "default" if default_reasoning else "effort %s" % kwargs["output_config"]["effort"]}
    return text, usage


def run_openai_api(spec, model, prompt, default_reasoning):
    base = (spec.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    body = {"model": model, "messages": [{"role": "system", "content": SHORT_SYSTEM}, {"role": "user", "content": prompt}]}
    effort = None
    if spec.get("reasoning_param", True):
        effort = spec.get("default_effort", "medium") if default_reasoning else (spec.get("reduced_effort") or CFG.d["reasoning"]["reduced_effort"])
        body["reasoning_effort"] = effort
    out = _post(base + "/chat/completions", body, {"Authorization": "Bearer " + _env_key(spec, "OPENAI_API_KEY")})
    ch = out["choices"][0]
    if ch.get("finish_reason") == "length":
        raise RuntimeError("truncated: finish_reason=length")
    u = out.get("usage", {})
    usage = {"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0),
             "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
             "model_reported": out.get("model", model), "reasoning_setting": "effort %s" % effort if effort else "n/a"}
    return ch["message"].get("content") or "", usage


def run_gemini_api(spec, model, prompt, default_reasoning):
    base = (spec.get("base_url") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    gen = {"maxOutputTokens": int(spec.get("max_output_tokens", MAX_OUTPUT_TOKENS)), "responseMimeType": "application/json"}
    if not default_reasoning and spec.get("reduced_generation_config"):
        gen.update(spec["reduced_generation_config"])
    body = {"systemInstruction": {"parts": [{"text": SHORT_SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": gen}
    out = _post("%s/models/%s:generateContent" % (base, model), body, {"x-goog-api-key": _env_key(spec, "GEMINI_API_KEY")})
    cand = (out.get("candidates") or [{}])[0]
    if cand.get("finishReason") == "MAX_TOKENS":
        raise RuntimeError("truncated: finishReason=MAX_TOKENS")
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
    u = out.get("usageMetadata", {})
    usage = {"input_tokens": u.get("promptTokenCount", 0), "output_tokens": u.get("candidatesTokenCount", 0),
             "reasoning_tokens": u.get("thoughtsTokenCount", 0), "model_reported": out.get("modelVersion", model),
             "reasoning_setting": "default" if default_reasoning else json.dumps(spec.get("reduced_generation_config") or "default")}
    return text, usage


def run_command(spec, model, prompt, default_reasoning):
    cmd = spec.get("command")
    if not cmd:
        raise RuntimeError("backend command needs `command` in the model entry")
    argv = [a.replace("{model}", model) for a in (cmd if isinstance(cmd, list) else shlex.split(cmd))]
    p = subprocess.run(argv, input=prompt, capture_output=True, text=True, timeout=3600)
    if p.returncode != 0:
        raise RuntimeError("command failed (%d): %s" % (p.returncode, p.stderr[-400:]))
    return p.stdout, {"model_reported": model, "reasoning_setting": "default" if default_reasoning else "reduced (caller's command)"}


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def manual_usage(spec, model, prompt, text, default_reasoning, how):
    return {"model_reported": "%s (%s)" % (spec.get("answered_by") or model, how),
            "reasoning_setting": "default" if default_reasoning else "reduced",
            "input_tokens": estimate_tokens(prompt), "output_tokens": estimate_tokens(text), "tokens_estimated": True}


def run_manual(spec, model, prompt, default_reasoning, call_id="call"):
    d = WS / "manual"
    d.mkdir(parents=True, exist_ok=True)
    pp, rp = d / ("%s.prompt.md" % call_id), d / ("%s.reply.json" % call_id)
    if rp.exists() and rp.stat().st_size:
        text = rp.read_text(encoding="utf-8")
        return text, manual_usage(spec, model, prompt, text, default_reasoning, "manual")
    pp.write_text(prompt, encoding="utf-8")
    raise ManualPending(str(pp))


def replay_dir(spec) -> Path:
    d = spec.get("replay_dir")
    if not d:
        raise RuntimeError("backend replay needs `replay_dir` (a folder of <call>.reply.json files)")
    return CFG.resolve(d)


def run_replay(spec, model, prompt, default_reasoning, call_id="call"):
    rp = replay_dir(spec) / ("%s.reply.json" % call_id)
    if not rp.exists():
        raise RuntimeError("replay: no recorded reply %s. The recording does not cover this call (was the config, "
                           "corpus or a human file changed?)" % rp)
    text = rp.read_text(encoding="utf-8")
    want = (RECORDED.get(str(rp.parent)) or {}).get(call_id)
    if want and want != sha(prompt.encode("utf-8")):
        print("   ! replay: the prompt for %s differs from the recorded one; the recorded reply is used anyway" % call_id)
    return text, manual_usage(spec, model, prompt, text, default_reasoning, "replay")


RECORDED = {}   # replay_dir -> {call_id: sha256 of the prompt it answered}, from <replay_dir>/index.json


def load_replay_index(spec):
    try:
        d = replay_dir(spec)
    except RuntimeError:
        return
    idx = d / "index.json"
    if str(d) not in RECORDED:
        RECORDED[str(d)] = {k: v.get("prompt_sha256") for k, v in json.loads(idx.read_text(encoding="utf-8")).get("calls", {}).items()} \
            if idx.exists() else {}


BACKENDS = {"claude_cli": run_claude_cli, "codex_cli": run_codex_cli, "anthropic_api": run_anthropic_api,
            "openai_api": run_openai_api, "gemini_api": run_gemini_api, "command": run_command}


# --------------------------------------------------------------------------- one call
def resolve_model(family: str, stage: str) -> tuple[dict, str, str]:
    spec = CFG.family_model(family)
    base_stage = stage.split(":")[0]
    # stage_models: the most specific key that names this stage or a prefix of it ("coding" covers
    # "coding-screened", "coding-adversary" and "coding-answer" unless they have their own entry)
    sm = spec.get("stage_models") or {}
    keys = sorted((k for k in sm if base_stage == k or base_stage.startswith(str(k) + "-")), key=len, reverse=True)
    model = (sm[keys[0]] if keys else None) or spec.get("model")
    if not model:
        raise SystemExit("config: models.%s has no `model`" % family)
    return spec, spec.get("backend", "claude_cli"), str(model)


def default_reasoning(stage: str) -> bool:
    base = stage.split(":")[0]
    return any(base == s or base.startswith(s + "-") for s in CFG.d["reasoning"]["default_stages"]) and not base.endswith("adversary")


def call(*, stage: str, role: str, family: str, brief: Path, inputs: list, outputs: list,
         batch: str = "-", instruction: str = "", root: Path | None = None, attempt: int = 0) -> dict:
    """Run one role. `outputs` are names the brief uses, or (name in brief, path to write) pairs;
    paths are relative to `root` (default: the workspace). `attempt` numbers follow-up calls of the
    same role on the same batch (repair and completeness rounds), so each gets its own call id."""
    root = root or WS
    prompt, hashes = build_prompt(brief, inputs, instruction)
    spec, backend, model = resolve_model(family, stage)
    dr = default_reasoning(stage)
    call_id = re.sub(r"[^\w.-]", "_", "%s__%s__%s" % (stage, role, batch) + ("__a%d" % attempt if attempt else "") + CALL_SUFFIX)
    if backend not in ("manual", "replay") and backend not in BACKENDS:
        raise SystemExit("config: unknown backend %r for family %s" % (backend, family))
    note, t0 = "", time.time()
    try:
        if backend == "manual":
            text, usage = run_manual(spec, model, prompt, dr, call_id)
        elif backend == "replay":
            load_replay_index(spec)
            text, usage = run_replay(spec, model, prompt, dr, call_id)
        else:
            text, usage = BACKENDS[backend](spec, model, prompt, dr)
    except ManualPending:
        raise
    except RuntimeError as e:
        if backend == "claude_cli" and str(e).startswith("truncated") and dr:
            log(stage, role, family, model, batch, time.time() - t0, {}, hashes, {}, "failed", str(e) + "; retried with thinking off")
            text, usage = run_claude_cli(spec, model, prompt, False)
            note = "retry after truncation, thinking off"
        else:
            log(stage, role, family, model, batch, time.time() - t0, {}, hashes, {}, "failed", str(e)[:300])
            raise
    secs = time.time() - t0
    raw = LOG.parent / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    raw_path = raw / ("%s_%s.txt" % (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"), call_id))
    raw_path.write_text(text, encoding="utf-8")
    try:
        obj = extract_json(text)
    except ValueError as e:
        log(stage, role, family, model, batch, secs, usage, hashes, {}, "failed", "unparseable reply saved to %s" % raw_path.name)
        raise RuntimeError("%s: %s" % (role, e))
    written = {}
    for spec_out in outputs:
        label, dest = spec_out if isinstance(spec_out, tuple) else (spec_out, spec_out)
        content = obj.get(label) if (len(outputs) > 1 or label in obj) else obj
        if content is None:
            key = next((k for k in obj if Path(k).name == Path(label).name), None)
            content = obj.get(key) if key else None
        if content is None:
            raise RuntimeError("%s: output %s missing from reply keys %s" % (role, label, list(obj)[:5]))
        path = Path(root) / str(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if str(dest).endswith(".jsonl"):
            if isinstance(content, str):
                txt = content.strip()
                try:
                    content = json.loads(txt)
                except json.JSONDecodeError:
                    content = [json.loads(l) for l in txt.splitlines() if l.strip().startswith("{")]
            rows = content if isinstance(content, list) else content.get("rows", content.get("units", []))
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        else:
            path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written[str(dest)] = sha(path.read_bytes())
    log(stage, role, family, model, batch, secs, usage, hashes, written, "ok", note, call_id=call_id,
        prompt_sha256=sha(prompt.encode("utf-8")))
    return obj


def log(stage, role, family, model, batch, secs, usage, in_hashes, out_hashes, status, note, call_id=None, prompt_sha256=None):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stage": stage, "role": role,
             "role_family": family, "model_id": model, "batch": batch, "wall_seconds": round(secs, 1),
             **{k: (usage or {}).get(k) for k in ("input_tokens", "output_tokens", "reasoning_tokens", "cached_input_tokens",
                                                  "model_reported", "reasoning_setting", "cost_usd_reported", "tokens_estimated")},
             "inputs_sha256": in_hashes, "outputs_sha256": out_hashes, "status": status, "note": note}
    if call_id:
        entry["call_id"] = call_id
    if prompt_sha256:
        entry["prompt_sha256"] = prompt_sha256
    with _lock, LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- decision model
def decide(state: dict, questions: dict, *, stage: str, role: str, batch: str = "-") -> dict:
    """One decision-model request: {question_id: probability_yes}. `questions` maps an id to
    {"code": {label, definition, include, exclude, ...}, "question": "<yes/no question>"}.
    Logged like any other call."""
    dm = CFG.d["decision_model"]
    t0 = time.time()
    if dm.get("backend", "typesafe") in ("manual", "replay"):
        return decide_by_file(dm, state, questions, stage=stage, role=role, batch=batch, t0=t0)
    if dm.get("backend", "typesafe") == "command":
        cmd = dm.get("command")
        argv = cmd if isinstance(cmd, list) else shlex.split(cmd or "")
        if not argv:
            raise SystemExit("decision_model.backend is command but decision_model.command is empty")
        req = json.dumps({"state": state, "questions": questions})
        p = subprocess.run(argv, input=req, capture_output=True, text=True, timeout=600)
        if p.returncode != 0:
            log(stage, role, "decision-model", "command", batch, time.time() - t0, {}, {"request": sha(req.encode())}, {}, "failed", p.stderr[-300:])
            raise RuntimeError("decision-model command failed: %s" % p.stderr[-300:])
        out = json.loads(p.stdout)
        probs = {k: (None if v is None else float(v)) for k, v in out.items()}
        log(stage, role, "decision-model", "command", batch, time.time() - t0, {"reasoning_setting": "n/a"},
            {"request": sha(req.encode())}, {}, "ok", "%d questions" % len(questions))
        return probs
    body = json.dumps({"state": state, "model": dm.get("model", "jev-latest"),
                       "questions": {k: {"type": "noul", "instructions": v} for k, v in questions.items()}}).encode()
    key = os.environ.get(dm.get("api_key_env") or "TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("environment variable %s is not set (decision_model.api_key_env)" % dm.get("api_key_env"))
    req = urllib.request.Request(dm["endpoint"], data=body, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as f:
                out = json.loads(f.read())
            break
        except Exception as e:  # transient service errors: back off and retry
            if attempt == 3:
                log(stage, role, "decision-model", dm.get("model"), batch, time.time() - t0, {}, {"request": sha(body)}, {}, "failed", str(e)[:300])
                raise
            time.sleep(2 ** attempt)
    u = out.get("usage", {})
    log(stage, role, "decision-model", out.get("model", dm.get("model")), batch, time.time() - t0,
        {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"), "model_reported": out.get("model"),
         "reasoning_setting": "n/a"}, {"request": sha(body)}, {}, "ok", "%d questions" % len(questions))
    return {k: v.get("noul") for k, v in out.get("answers", {}).items()}


DM_PROMPT = """# Decision-model request (answer as a calibrated yes/no model)

For each question id below, give the probability (a number from 0 to 1) that the answer to its
`question` is yes for this {unit}, judging only the unit text in `state` against the code's label,
definition, include and exclude clauses. Use null when you cannot answer. No text, no reasons.

Reply with ONE JSON object and nothing else, saved as `{reply}` next to this file:
{{"<question id>": 0.83, "<question id>": 0.02}}

=== REQUEST ===
{request}
"""


def decide_by_file(dm, state, questions, *, stage, role, batch, t0):
    """Decision model answered by hand (manual) or from a recording (replay). Same contract as `command`."""
    call_id = re.sub(r"[^\w.-]", "_", "%s__%s__%s" % (stage, role, batch) + CALL_SUFFIX)
    req = json.dumps({"state": state, "questions": questions}, ensure_ascii=False, indent=1)
    if dm.get("backend") == "manual":
        d = WS / "manual"
        d.mkdir(parents=True, exist_ok=True)
        rp = d / ("%s.reply.json" % call_id)
        if not (rp.exists() and rp.stat().st_size):
            (d / ("%s.prompt.md" % call_id)).write_text(DM_PROMPT.format(unit=CFG.study["unit_name"], reply=rp.name, request=req), encoding="utf-8")
            raise ManualPending(str(d / ("%s.prompt.md" % call_id)))
        how = "manual"
    else:
        spec = dict(dm)
        load_replay_index(spec)
        rp = replay_dir(spec) / ("%s.reply.json" % call_id)
        if not rp.exists():
            raise RuntimeError("replay: no recorded decision-model reply %s" % rp)
        want = (RECORDED.get(str(rp.parent)) or {}).get(call_id)
        if want and want != sha(req.encode()):
            print("   ! replay: the decision-model request %s differs from the recorded one; the recorded reply is used anyway" % call_id)
        how = "replay"
    text = rp.read_text(encoding="utf-8")
    try:
        out = extract_json(text)
    except ValueError as e:
        log(stage, role, "decision-model", dm.get("model"), batch, time.time() - t0, {}, {"request": sha(req.encode())}, {}, "failed", str(e))
        raise RuntimeError("decision model reply %s: %s" % (rp.name, e))
    probs = {}
    for k in questions:
        v = out.get(k)
        probs[k] = None if v is None else min(1.0, max(0.0, float(v)))
    log(stage, role, "decision-model", dm.get("model"), batch, time.time() - t0,
        {"reasoning_setting": "n/a", "model_reported": "%s (%s)" % (dm.get("answered_by") or dm.get("model"), how),
         "input_tokens": estimate_tokens(req), "output_tokens": 0, "tokens_estimated": True},
        {"request": sha(req.encode())}, {}, "ok", "%d questions" % len(questions), call_id=call_id, prompt_sha256=sha(req.encode()))
    return probs
