#!/usr/bin/env python3
"""
`council.py --config config.yaml doctor`: check that this computer is ready to run the council,
without spending anything.

It checks the Python version, that the config loads and passes its check, each model family's
prerequisites (the CLI is on the PATH and, where it can tell, logged in; the API key's environment
variable is set; a local server answers; the Python package is installed), the decision-model
setting, that the corpus can be read, and that the workspace can be written. It prints a pass/fail
checklist with the fix for each failure, and exits with status 1 if anything failed.

It never prints, stores or sends a key: for a key it reports only whether the environment variable
named in the config is set. Nothing is sent to a model unless you pass --ping, which sends one
trivial request (a few tokens) to each family and to the decision model to prove the connection
works end to end.

    python3 pipeline/council.py --config config.yaml doctor
    python3 pipeline/council.py --config config.yaml doctor --ping     # one tiny paid request per family
    python3 pipeline/council.py --config config.yaml doctor --json     # for programs (the app uses it)
    python3 pipeline/council.py doctor                                 # no config yet: general checks only

Standard library only.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

SETUP = "SETUP.md"
KEY_DEFAULTS = {"anthropic_api": "ANTHROPIC_API_KEY", "openai_api": "OPENAI_API_KEY", "gemini_api": "GEMINI_API_KEY"}
KEY_HELP = {
    "anthropic_api": "create a key in the Anthropic Console (console.anthropic.com, Settings > API keys)",
    "openai_api": "create a key on the OpenAI platform (platform.openai.com/api-keys)",
    "gemini_api": "create a key in Google AI Studio (aistudio.google.com/apikey)",
    "typesafe": "get a key from TypeSafe (typesafe.ai)",
}
FAMILY_SECTION = {"anthropic_api": "Claude", "claude_cli": "Claude", "openai_api": "GPT", "codex_cli": "GPT", "gemini_api": "Gemini"}
PING_PROMPT = 'Reply with exactly this JSON object and nothing else: {"ok": true}'


class Report:
    def __init__(self):
        self.items = []

    def add(self, group, status, name, detail="", fix=""):
        self.items.append(OrderedDict([("group", group), ("status", status), ("name", name), ("detail", detail), ("fix", fix)]))

    def count(self, status):
        return sum(1 for i in self.items if i["status"] == status)


def set_hint(var: str) -> str:
    return ("set it in the terminal you run the pipeline from: macOS or Linux `export %s=\"...\"`, Windows PowerShell "
            "`$env:%s = \"...\"` (to keep it, see %s, \"Keep a key set\"); never put the key in config.yaml" % (var, var, SETUP))


def env_is_set(var: str) -> bool:
    return bool(os.environ.get(var or ""))


def run_quiet(argv, timeout=20):
    """Run a command and return (exit code, stdout); output is never printed (it may name the account)."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return None, ""


# --------------------------------------------------------------------------- per backend
def check_claude_cli(rep, group, spec):
    binary = spec.get("binary") or os.environ.get("CLAUDE_BIN", "claude")
    path = shutil.which(binary)
    if not path:
        rep.add(group, "fail", "Claude Code CLI (`%s`) is not on the PATH" % binary, "",
                "install Claude Code (%s, \"Claude\", route B), open a new terminal and run `claude` once to log in; "
                "or switch this family to `backend: anthropic_api` with an API key (route A)" % SETUP)
        return
    rep.add(group, "pass", "Claude Code CLI found", path)
    code, out = run_quiet([binary, "auth", "status", "--json"])
    logged = None
    try:
        obj = json.loads(out) if out.strip() else None
        if isinstance(obj, dict):
            for k in ("loggedIn", "logged_in", "authenticated"):
                if k in obj:
                    logged = bool(obj[k])
    except ValueError:
        pass
    if logged is None and code is not None:
        logged = code == 0 if out.strip() else None
    if env_is_set("ANTHROPIC_API_KEY"):
        rep.add(group, "info", "ANTHROPIC_API_KEY is set in this environment; the Claude CLI may use it (billed per token) instead of your login")
    if logged is True:
        rep.add(group, "pass", "Claude Code CLI is logged in")
    elif logged is False:
        rep.add(group, "fail", "Claude Code CLI is not logged in", "", "run `claude` (or `claude auth login`) once and sign in, then run doctor again")
    else:
        rep.add(group, "warn", "could not tell whether the Claude Code CLI is logged in", "",
                "run `claude auth status`; if it says you are not logged in, run `claude` once and sign in")


def check_codex_cli(rep, group, spec):
    binary = spec.get("binary") or os.environ.get("CODEX_BIN", "codex")
    path = shutil.which(binary)
    if not path:
        rep.add(group, "fail", "Codex CLI (`%s`) is not on the PATH" % binary, "",
                "install the Codex CLI (%s, \"GPT\", route B), open a new terminal and run `codex login`; "
                "or switch this family to `backend: openai_api` with an API key (route A)" % SETUP)
        return
    rep.add(group, "pass", "Codex CLI found", path)
    code, out = run_quiet([binary, "login", "status"])
    if code == 0:
        rep.add(group, "pass", "Codex CLI is logged in")
    elif code is None:
        rep.add(group, "warn", "could not tell whether the Codex CLI is logged in", "", "run `codex login status`; if needed, `codex login`")
    else:
        rep.add(group, "fail", "Codex CLI is not logged in", "", "run `codex login` and sign in, then run doctor again")


def check_key(rep, group, spec, backend):
    var = spec.get("api_key_env") or KEY_DEFAULTS.get(backend, "")
    if not var:
        rep.add(group, "fail", "no `api_key_env` for this family", "", "add `api_key_env: <VARIABLE_NAME>` to this family in config.yaml")
        return
    if env_is_set(var):
        rep.add(group, "pass", "%s is set in this environment" % var, "(the value is not shown)")
    else:
        local = backend == "openai_api" and is_local(spec.get("base_url"))
        rep.add(group, "fail", "%s is not set in this environment" % var, "",
                ("a local server usually ignores the key, but the variable must exist: `export %s=none` (Windows PowerShell: "
                 "`$env:%s = \"none\"`)" % (var, var)) if local else
                "%s, then %s" % (KEY_HELP.get(backend, "get an API key from the vendor"), set_hint(var)))


def is_local(url) -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost")


def port_open(url) -> bool:
    u = urlparse(url)
    port = u.port or (443 if u.scheme == "https" else 80)
    try:
        with socket.create_connection((u.hostname, port), timeout=2):
            return True
    except OSError:
        return False


def check_family(rep, cfg, fam, roles):
    group = "Family %s (%s)" % (fam, ", ".join(roles))
    spec = (cfg.d.get("models") or {}).get(fam) or {}
    if not spec:
        rep.add(group, "fail", "no entry under `models` for family %r" % fam, "", "add `models: %s: {backend: ..., model: ...}` (see config.example.yaml)" % fam)
        return
    b = spec.get("backend", "claude_cli")
    model = str(spec.get("model") or "")
    rep.add(group, "info", "backend %s, model %s" % (b, model or "(not set)"))
    if not model or "REPLACE" in model:
        rep.add(group, "fail", "the model id is not set", "", "write the model id you use under models.%s.model (%s lists where to find it)" % (fam, SETUP))
    if b == "claude_cli":
        check_claude_cli(rep, group, spec)
    elif b == "codex_cli":
        check_codex_cli(rep, group, spec)
    elif b in ("anthropic_api", "openai_api", "gemini_api"):
        if b == "anthropic_api":
            try:
                import anthropic  # type: ignore  # noqa: F401
                rep.add(group, "pass", "the `anthropic` Python package is installed")
            except ImportError:
                rep.add(group, "fail", "the `anthropic` Python package is not installed", "", "run `python3 -m pip install anthropic`")
        if spec.get("api_key"):
            rep.add(group, "fail", "this family holds `api_key` in the config", "", "delete the key from config.yaml, put it in an environment variable and name the variable in `api_key_env`")
        check_key(rep, group, spec, b)
        if b == "openai_api" and spec.get("base_url"):
            if is_local(spec["base_url"]):
                if port_open(spec["base_url"]):
                    rep.add(group, "pass", "the local server at %s accepts connections" % spec["base_url"])
                else:
                    rep.add(group, "fail", "nothing answers at %s" % spec["base_url"], "", "start your local model server (Ollama, vLLM, LM Studio, ...) and check the port")
                if spec.get("reasoning_param", True):
                    rep.add(group, "warn", "`reasoning_param` is not false", "", "most local servers reject `reasoning_effort`; add `reasoning_param: false` to this family")
            else:
                rep.add(group, "info", "OpenAI-compatible endpoint %s" % spec["base_url"])
    elif b == "command":
        cmd = spec.get("command")
        argv = cmd if isinstance(cmd, list) else (cmd or "").split()
        if not argv:
            rep.add(group, "fail", "backend command needs `command`", "", "add `command: [\"program\", \"arg\"]` to this family")
        elif shutil.which(argv[0]) or Path(argv[0]).exists():
            rep.add(group, "pass", "the command `%s` exists" % argv[0], "use --ping to check that it reads the prompt on stdin and prints a reply")
        else:
            rep.add(group, "fail", "the command `%s` is not found" % argv[0], "", "install it or give its full path")
    elif b == "manual":
        rep.add(group, "info", "manual: each prompt is written to <workspace>/manual/ for you or an agent to answer; no key needed")
        if not spec.get("answered_by"):
            rep.add(group, "warn", "`answered_by` is empty", "", "say which model will answer these prompts (for example `answered_by: \"Claude Opus 5\"`); it goes in the report")
    elif b == "replay":
        d = cfg.resolve(spec.get("replay_dir") or "")
        if spec.get("replay_dir") and d.is_dir():
            n = len(list(d.glob("*.reply.json")))
            rep.add(group, "pass", "replay: %d recorded replies in %s" % (n, spec["replay_dir"]), "no model is contacted")
        else:
            rep.add(group, "fail", "replay_dir %r is missing" % spec.get("replay_dir"), "", "point `replay_dir` at a folder written by `council.py export-replies`")
    else:
        rep.add(group, "fail", "unknown backend %r" % b, "", "use one of %s" % ", ".join(C.BACKENDS))


def families_in_use(cfg) -> "OrderedDict[str, list]":
    use = OrderedDict()

    def add(f, role):
        use.setdefault(f, []).append(role)
    for k, f in cfg.analysts.items():
        add(f, "analyst %s" % k)
    add(cfg.reconciler, "reconciler")
    for k, f in cfg.coders.items():
        add(f, "coder %s" % k)
    if cfg.full:
        for k, f in cfg.analyst_adversary.items():
            add(f, "adversary of %s" % k)
        if cfg.recon_adversary:
            add(cfg.recon_adversary, "reconciliation adversary")
        for k, f in cfg.coder_adversary.items():
            add(f, "adversary of coder %s" % k)
    for f in use:
        roles = use[f]
        short = [r for r in roles if not r.startswith("adversary")]
        n_adv = len(roles) - len(short)
        use[f] = short + (["%d adversary role%s" % (n_adv, "" if n_adv == 1 else "s")] if n_adv else [])
    return use


def check_decision_model(rep, cfg):
    group = "Decision model"
    dm = cfg.d["decision_model"]
    if not cfg.full:
        rep.add(group, "info", "not used in Lite mode")
        return
    if not dm.get("enabled"):
        rep.add(group, "info", "Full without a decision model (`enabled: false`): the adversaries run, screening and leads are off")
        return
    b = dm.get("backend", "typesafe")
    if b == "typesafe":
        var = dm.get("api_key_env") or "TYPESAFE_API_KEY"
        rep.add(group, "info", "TypeSafe %s at %s" % (dm.get("model"), dm.get("endpoint")))
        if env_is_set(var):
            rep.add(group, "pass", "%s is set in this environment" % var, "(the value is not shown)")
        else:
            rep.add(group, "fail", "%s is not set in this environment" % var, "",
                    "%s and set %s in the terminal you run the pipeline from (never in config.yaml); or run Full without it "
                    "(`decision_model: {enabled: false}`); or use `backend: manual` (an agent or you answer each request; not calibrated). "
                    "See %s, \"The decision model\"" % (KEY_HELP["typesafe"], var, SETUP))
    elif b == "command":
        cmd = dm.get("command")
        argv = cmd if isinstance(cmd, list) else (cmd or "").split()
        if argv and (shutil.which(argv[0]) or Path(argv[0]).exists()):
            rep.add(group, "pass", "the command `%s` exists" % argv[0])
        else:
            rep.add(group, "fail", "decision_model.command is empty or not found", "", "give a program that reads {state, questions} on stdin and prints {id: probability}")
    elif b == "manual":
        rep.add(group, "warn", "manual decision model: one request per unit per analyst and per unit at coding, answered by hand or by an agent; not calibrated",
                "", "use TypeSafe Jev (a key) for calibrated scores, or set `enabled: false`")
    elif b == "replay":
        d = cfg.resolve(dm.get("replay_dir") or "")
        rep.add(group, "pass" if dm.get("replay_dir") and d.is_dir() else "fail", "replay from %s" % dm.get("replay_dir"), "",
                "" if d.is_dir() else "point decision_model.replay_dir at the recorded replies")
    else:
        rep.add(group, "fail", "unknown decision-model backend %r" % b, "", "use one of %s" % ", ".join(C.DM_BACKENDS))


def check_corpus(rep, cfg):
    group = "Data"
    p = cfg.corpus_csv
    if not p.exists():
        rep.add(group, "fail", "corpus not found: %s" % p, "", "put your CSV there or change `study.corpus_csv` (columns uid,text)")
        return
    try:
        csv.field_size_limit(10 ** 9)
        with open(p, newline="", encoding="utf-8-sig") as fh:
            r = csv.DictReader(fh)
            cols = r.fieldnames or []
            n = sum(1 for _ in r)
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        rep.add(group, "fail", "the corpus cannot be read: %s" % e, "", "save it as UTF-8 CSV")
        return
    if "uid" not in cols or "text" not in cols:
        rep.add(group, "fail", "the corpus needs columns `uid` and `text` (it has %s)" % ", ".join(cols), "", "rename the columns or add them")
    else:
        rep.add(group, "pass", "corpus %s: %d units" % (p.name, n))
    gov = str(cfg.d.get("data_governance") or "")
    if not gov.strip() or "REPLACE" in gov:
        rep.add(group, "warn", "`data_governance` is not filled in", "",
                "write what leaves this computer, to which vendors, under which consent terms; de-identify the corpus first (%s, \"Before any data leaves your computer\")" % SETUP)
    else:
        rep.add(group, "pass", "data_governance is recorded")


def check_workspace(rep, cfg):
    group = "Workspace"
    ws = cfg.workspace
    probe = ws
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        fd, name = tempfile.mkstemp(prefix=".council-doctor-", dir=str(probe))
        os.close(fd)
        os.remove(name)
        shown = os.path.normpath(str(ws))
        rep.add(group, "pass", "can write to %s" % (shown if ws.exists() else "%s (it will be created)" % shown))
    except OSError as e:
        rep.add(group, "fail", "cannot write to %s: %s" % (probe, e.strerror or e), "", "choose a `workspace` folder you can write to")


# --------------------------------------------------------------------------- --ping
def ping_family(rep, cfg, fam, roles):
    import models
    group = "Ping (one tiny request each)"
    spec = (cfg.d.get("models") or {}).get(fam) or {}
    b = spec.get("backend", "claude_cli")
    if b in ("manual", "replay"):
        rep.add(group, "info", "family %s: skipped, the %s backend contacts no model" % (fam, b))
        return
    if b not in models.BACKENDS:
        return
    t0 = time.time()
    try:
        text, _usage = models.BACKENDS[b](spec, str(spec.get("model")), PING_PROMPT, False)
        obj = models.extract_json(text)
        ok = obj.get("ok") is True
        rep.add(group, "pass" if ok else "warn", "family %s: the model replied in %.1f s%s" % (fam, time.time() - t0, "" if ok else ", but not with the JSON asked for"),
                "", "" if ok else "the model answered; check that it returns JSON only")
    except Exception as e:  # noqa: BLE001
        msg = str(e).replace("\n", " ")[:240]
        rep.add(group, "fail", "family %s: %s" % (fam, msg), "", "fix the error above (key, login, model id or network), then run doctor --ping again")


def ping_decision_model(rep, cfg):
    dm = cfg.d["decision_model"]
    if not (cfg.full and dm.get("enabled")) or dm.get("backend", "typesafe") not in ("typesafe", "command"):
        return
    group = "Ping (one tiny request each)"
    q = {"ping": {"code": {"label": "Mentions a cat", "definition": "The text mentions a cat."}, "question": "Does the text mention a cat?"}}
    state = {"unit_text": "My cat sleeps on the keyboard."}
    t0 = time.time()
    try:
        if dm.get("backend", "typesafe") == "command":
            cmd = dm.get("command")
            argv = cmd if isinstance(cmd, list) else (cmd or "").split()
            p = subprocess.run(argv, input=json.dumps({"state": state, "questions": q}), capture_output=True, text=True, timeout=120)
            if p.returncode != 0:
                raise RuntimeError("exit %d: %s" % (p.returncode, p.stderr[-200:]))
            out = json.loads(p.stdout)
            val = out.get("ping")
        else:
            import urllib.request
            key = os.environ.get(dm.get("api_key_env") or "TYPESAFE_API_KEY")
            if not key:
                raise RuntimeError("the key variable is not set")
            body = json.dumps({"state": state, "model": dm.get("model", "jev-latest"),
                               "questions": {k: {"type": "noul", "instructions": v} for k, v in q.items()}}).encode()
            req = urllib.request.Request(dm["endpoint"], data=body, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as f:
                out = json.loads(f.read())
            val = (out.get("answers", {}).get("ping") or {}).get("noul")
        ok = isinstance(val, (int, float))
        rep.add(group, "pass" if ok else "warn", "decision model: replied in %.1f s%s" % (time.time() - t0, " with a probability" if ok else " without a probability"))
    except Exception as e:  # noqa: BLE001
        rep.add(group, "fail", "decision model: %s" % str(e).replace("\n", " ")[:240], "", "check the key, the endpoint and the network, then run doctor --ping again")


# --------------------------------------------------------------------------- general checks (no config)
def general(rep):
    group = "Tools on this computer"
    for name, binary, hint in (("Claude Code CLI", "claude", "Claude, route B"), ("Codex CLI", "codex", "GPT, route B")):
        path = shutil.which(binary)
        rep.add(group, "pass" if path else "info", "%s %s" % (name, "found" if path else "not found"), path or "",
                "" if path else "only needed if you reach that family through its CLI (%s, \"%s\")" % (SETUP, hint))
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "TYPESAFE_API_KEY"):
        rep.add(group, "pass" if env_is_set(var) else "info", "%s %s" % (var, "is set" if env_is_set(var) else "is not set"),
                "(the value is not shown)" if env_is_set(var) else "", "" if env_is_set(var) else "only needed for that vendor's API route (%s)" % SETUP)


def run_checks(config_path=None, ping=False, search=True) -> dict:
    """Every check, as {config, ping, items: [{group, status, name, detail, fix}], n_pass, n_fail, n_warn}.
    With no config_path, a config.yaml in the current folder is used when `search` is true."""
    rep = Report()
    v = sys.version_info
    rep.add("Python", "pass" if v >= (3, 9) else "fail", "Python %d.%d.%d" % v[:3], "(3.9 or newer needed)",
            "" if v >= (3, 9) else "install Python 3.9 or newer (python.org) and run the pipeline with it")
    try:
        import openpyxl  # type: ignore  # noqa: F401
        rep.add("Python", "pass", "openpyxl installed (Excel packets for the researchers)")
    except ImportError:
        rep.add("Python", "info", "openpyxl not installed: researcher packets are CSV only", "", "optional: `python3 -m pip install openpyxl` for Excel workbooks")
    cfg = None
    if config_path is None and search:
        for cand in ("config.yaml", "config.yml", "config.json"):
            if Path(cand).exists():
                config_path = cand
                break
    if config_path is None:
        rep.add("Config", "warn", "no config file", "", "copy config.example.yaml to config.yaml and edit it, or save one from the app's Start page; then pass --config")
        general(rep)
    else:
        try:
            cfg = C.load(config_path)
            rep.add("Config", "pass", "%s loads (mode %s)" % (config_path, cfg.mode))
        except SystemExit as e:
            rep.add("Config", "fail", "the config does not load: %s" % e, "", "fix the line it names (compare with config.example.yaml)")
        except Exception as e:  # noqa: BLE001
            rep.add("Config", "fail", "the config does not load: %s" % e, "", "fix the YAML (indentation, quotes) and compare with config.example.yaml")
    if cfg:
        errs, warns = cfg.check()
        for e in errs:
            if "model is not set" in e or "has no entry under `models`" in e or e.startswith("corpus not found") or "api_key" in e:
                continue  # reported with its family or the data below, with a fix
            rep.add("Config", "fail", e, "", "edit config.yaml (config.example.yaml documents every key)")
        for w in warns:
            rep.add("Config", "warn", w)
        if not errs:
            rep.add("Config", "pass", "the config check passes")
        for fam, roles in families_in_use(cfg).items():
            check_family(rep, cfg, fam, roles)
        if len(set(cfg.analysts.values())) < 3:
            rep.add("Config", "warn", "fewer than three model families among the analysts", "", "the method uses three families; record the vendor caveat if you cannot")
        check_decision_model(rep, cfg)
        check_corpus(rep, cfg)
        check_workspace(rep, cfg)
        if ping:
            import models
            models.configure(cfg)
            for fam, roles in families_in_use(cfg).items():
                ping_family(rep, cfg, fam, roles)
            ping_decision_model(rep, cfg)
    return OrderedDict([("config", str(config_path) if config_path else None), ("ping", ping), ("items", rep.items),
                        ("n_pass", rep.count("pass")), ("n_fail", rep.count("fail")), ("n_warn", rep.count("warn"))])


MARK = {"pass": "PASS", "fail": "FAIL", "warn": "WARN", "info": "info"}


def print_report(res):
    print("council doctor: %s%s" % (res["config"] or "no config", " (with --ping)" if res["ping"] else ""))
    group = None
    for i in res["items"]:
        if i["group"] != group:
            group = i["group"]
            print("\n%s" % group)
        print("  [%s] %s%s" % (MARK[i["status"]], i["name"], ("  " + i["detail"]) if i["detail"] else ""))
        if i["fix"] and i["status"] in ("fail", "warn"):
            print("         fix: %s" % i["fix"])
    print("\n%d passed, %d failed, %d warning%s.%s" % (res["n_pass"], res["n_fail"], res["n_warn"], "" if res["n_warn"] == 1 else "s",
          " Fix the FAIL lines, then run doctor again." if res["n_fail"] else
          (" Ready. `--ping` sends one tiny request per family to prove the connection." if not res["ping"] else " Ready.")))


def main(args) -> int:
    res = run_checks(args.config, ping=getattr(args, "ping", False))
    if getattr(args, "json", False):
        print(json.dumps(res, indent=1))
    else:
        print_report(res)
    return 1 if res["n_fail"] else 0
