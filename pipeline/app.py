#!/usr/bin/env python3
"""
A local web app for running the council without a terminal or a coding agent.

    python3 pipeline/app.py            # then open the printed address, http://127.0.0.1:8765/
    python3 pipeline/app.py --port 9000 --open

Pages
  Start    try the offline demo; connect your models (the `council.py doctor` checks: CLI logins, API key
           variables set or not, never their values; SETUP.md at /doc); choose Lite or Full, upload or point
           to a CSV (uid,text), enter the research questions, pick the model families and backends (API keys
           are named by their environment variable, never typed in), save config.yaml; or open a config
  Run      every stage with its status (`council.py status`), a button that runs the stage's command
           in the background with a live log, and a "waiting for researchers" card at each human stop
           with links to the packets and dashboards and a place to put what the researchers return
  Results  the run's results dashboard (dashboard.html), RESULTS.md and the reliability report

The app only runs the pipeline's own commands (the ones `council.py status` lists), listens on
127.0.0.1 only, refuses requests whose Host is not local, and requires a per-session token on every
change, so a web page in another tab cannot drive it. It never reads, stores or displays a key: for
each key it shows only whether the environment variable it names is set.

Standard library only. Works offline (no CDN).
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

PIPE = Path(__file__).resolve().parent
REPO = PIPE.parent
sys.path.insert(0, str(PIPE))
import config as C  # noqa: E402

TOKEN = secrets.token_urlsafe(24)
PORT = 8765
DEMO_CONFIG = REPO / "examples" / "tiny" / "config.yaml"
MAX_UPLOAD = 50 * 1024 * 1024
BACKENDS = [("claude_cli", "Claude Code CLI (claude)"), ("codex_cli", "Codex CLI (codex)"), ("anthropic_api", "Anthropic API"),
            ("openai_api", "OpenAI or OpenAI-compatible API"), ("gemini_api", "Gemini API"), ("command", "Any program (command)"),
            ("manual", "Manual: prompts are answered by hand or by an agent")]
KEY_BACKENDS = {"anthropic_api": "ANTHROPIC_API_KEY", "openai_api": "OPENAI_API_KEY", "gemini_api": "GEMINI_API_KEY"}

STATE = {"config": None}
JOB = {"id": 0, "running": False, "step": None, "label": "", "log": [], "exit": None, "started": None, "ended": None}
JOB_LOCK = threading.Lock()


def initial_config():
    for c in (REPO / "config.yaml", REPO / "config.yml", REPO / "config.json"):
        if c.exists():
            return c
    return None


# --------------------------------------------------------------------------- YAML writer (read back by config.py, with or without PyYAML)
def _key(k) -> str:
    k = str(k)
    return k if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", k) else json.dumps(k)


def _scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return json.dumps(str(v), ensure_ascii=False)


def _flow(v) -> str:
    if isinstance(v, dict):
        return "{" + ", ".join("%s: %s" % (_key(k), _flow(x)) for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(_flow(x) for x in v) + "]"
    return _scalar(v)


def to_yaml(d, indent=0) -> str:
    pad = " " * indent
    out = []
    for k, v in d.items():
        if isinstance(v, dict) and v and any(isinstance(x, (dict, list)) for x in v.values()):
            out.append("%s%s:" % (pad, _key(k)))
            out.append(to_yaml(v, indent + 2))
        elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            out.append("%s%s:" % (pad, _key(k)))
            for item in v:
                first = True
                for ik, iv in item.items():
                    out.append("%s  %s%s: %s" % (pad, "- " if first else "  ", _key(ik), _flow(iv)))
                    first = False
        else:
            out.append("%s%s: %s" % (pad, _key(k), _flow(v)))
    return "\n".join(out)


def build_config(f: dict, config_path: Path) -> str:
    """The form's fields -> config.yaml text."""
    fams = []
    for i, fam in enumerate(f.get("families") or [], 1):
        name = re.sub(r"[^A-Za-z0-9_-]", "", fam.get("name") or "") or "family%d" % i
        spec = {"backend": fam.get("backend") or "manual", "model": (fam.get("model") or "").strip() or "REPLACE_WITH_MODEL_ID"}
        if spec["backend"] in KEY_BACKENDS or (fam.get("api_key_env") or "").strip():
            spec["api_key_env"] = re.sub(r"[^A-Za-z0-9_]", "", fam.get("api_key_env") or "") or KEY_BACKENDS.get(spec["backend"], "API_KEY")
        if (fam.get("base_url") or "").strip():
            spec["base_url"] = fam["base_url"].strip()
        if spec["backend"] == "command" and (fam.get("command") or "").strip():
            spec["command"] = fam["command"].strip()
        if spec["backend"] == "manual":
            spec["answered_by"] = (fam.get("answered_by") or "").strip() or spec["model"]
        fams.append((name, spec))
    if len(fams) != 3 or len({n for n, _ in fams}) != 3:
        raise ValueError("three model families with three different names are needed")
    names = [n for n, _ in fams]
    rqs = []
    for i, q in enumerate(f.get("rqs") or [], 1):
        if (q.get("text") or "").strip():
            item = {"id": (q.get("id") or "").strip() or "RQ%d" % i, "text": q["text"].strip()}
            if (q.get("rationale") or "").strip():
                item["rationale"] = q["rationale"].strip()
            rqs.append(item)
    if not rqs:
        raise ValueError("enter at least one research question")
    corpus = Path(f.get("corpus_csv") or "")
    if not str(corpus).strip():
        raise ValueError("choose a corpus CSV")
    try:
        corpus_rel = str(corpus.resolve().relative_to(config_path.parent.resolve()))
    except ValueError:
        corpus_rel = str(corpus.resolve())
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", (f.get("study_name") or "my-study").strip()).strip("-") or "my-study"
    d = {"mode": "full" if f.get("mode") == "full" else "lite", "workspace": "runs/%s" % slug,
         "study": {"corpus_csv": corpus_rel, "unit_name": f.get("unit_name") or "response", "unit_name_plural": f.get("unit_name_plural") or "responses",
                   "respondent_name": f.get("respondent_name") or "respondent", "respondent_name_plural": f.get("respondent_name_plural") or "respondents",
                   "corpus_description": (f.get("corpus_description") or "").strip(), "scope_rule": (f.get("scope_rule") or "").strip() or
                   "Code only what a respondent states in the unit.", "topic_phrase": f.get("topic_phrase") or "", "research_questions": rqs},
         "roles": {"analysts": {"A": names[0], "B": names[1], "C": names[2]}, "reconciler": names[0], "reconciliation_adversary": names[1],
                   "coders": {"1": names[0], "2": names[1], "3": names[2]}},
         "models": {n: s for n, s in fams}}
    dm = f.get("decision_model") or {}
    if d["mode"] == "full":
        if dm.get("enabled"):
            dd = {"enabled": True, "backend": dm.get("backend") or "typesafe"}
            if dd["backend"] == "typesafe":
                dd.update(endpoint="https://api.typesafe.ai/v1/systemone", model="jev-latest",
                          api_key_env=re.sub(r"[^A-Za-z0-9_]", "", dm.get("api_key_env") or "") or "TYPESAFE_API_KEY")
            elif dd["backend"] == "command":
                if not (dm.get("command") or "").strip():
                    raise ValueError("the decision model's command is empty")
                dd.update(command=dm["command"].strip(), model=dm.get("model") or "command")
            else:
                dd.update(model=dm.get("model") or "decision-model", answered_by=dm.get("answered_by") or "")
            d["decision_model"] = dd
        else:
            d["decision_model"] = {"enabled": False}
    d["batch_size"] = 25
    d["data_governance"] = (f.get("data_governance") or "").strip() or "REPLACE: what leaves the machine, to which vendors, under which terms"
    head = ("# Written by pipeline/app.py. Every relative path is resolved against this file's folder.\n"
            "# All settings and their defaults: config.example.yaml. API keys are named here by their environment\n"
            "# variable (api_key_env); the keys themselves stay in your environment.\n\n")
    return head + to_yaml(d) + "\n"


# --------------------------------------------------------------------------- jobs
def py(script, *args):
    return [sys.executable, str(PIPE / script)] + list(args)


def run_job(label, argv, step=None, after=None):
    with JOB_LOCK:
        if JOB["running"]:
            return False
        JOB.update(id=JOB["id"] + 1, running=True, step=step, label=label, log=["$ " + " ".join(
            [os.path.relpath(a, REPO) if os.path.isabs(a) and a.startswith(str(REPO)) else a for a in ["python3"] + argv[1:]])],
            exit=None, started=time.time(), ended=None)

    def work():
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        try:
            p = subprocess.Popen(argv, cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, bufsize=1)
            for line in p.stdout:
                with JOB_LOCK:
                    JOB["log"].append(line.rstrip("\n"))
                    if len(JOB["log"]) > 5000:
                        del JOB["log"][1:1000]
            code = p.wait()
        except Exception as e:  # noqa: BLE001
            with JOB_LOCK:
                JOB["log"].append("could not start: %s" % e)
            code = -1
        if after:
            after(code)
        with JOB_LOCK:
            JOB.update(running=False, exit=code, ended=time.time())

    threading.Thread(target=work, daemon=True).start()
    return True


def status():
    cfg = STATE["config"]
    if not cfg or not Path(cfg).exists():
        return {"error": "no config yet: fill in the Start page and save it, or open an existing config, or try the demo"}
    p = subprocess.run(py("council.py", "--config", str(cfg), "status", "--json"), cwd=str(REPO), capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        return {"error": (p.stderr or p.stdout).strip()[-2000:] or "status failed"}
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"error": p.stdout[-2000:]}


def doctor_checks(ping=False):
    """The `council.py doctor` checks on the open config (general checks if none is open). Keys are never read out."""
    import doctor
    cfg = STATE["config"]
    try:
        res = doctor.run_checks(str(cfg) if cfg else None, ping=ping, search=False)
    except Exception as e:  # noqa: BLE001
        return {"error": "the check failed: %s" % e}
    if cfg:
        res["config"] = os.path.relpath(cfg, REPO) if str(cfg).startswith(str(REPO)) else str(cfg)
    return res


def workspace():
    cfg = STATE["config"]
    if not cfg:
        return None
    try:
        return C.load(cfg).workspace
    except SystemExit:
        return None


def inside(base: Path, rel: str):
    try:
        p = (base / rel).resolve()
        p.relative_to(base.resolve())
        return p
    except (ValueError, OSError):
        return None


# --------------------------------------------------------------------------- tiny Markdown and CSV views
BASE = threading.local()


DOCS = ("SETUP.md", "README.md", "AGENTS.md", "CHECKLIST.md", "examples/tiny/README.md", "examples/zhang2023/README.md",
        "examples/zhang2023/data/ATTRIBUTION.md")


def md_link(target: str) -> str:
    """A link in a Markdown file -> an external address, the app's view of a repository document (on /doc pages),
    or the app's view of a workspace file."""
    if re.match(r"^https?://[^\s\"'<>]+$", target):
        return target
    if getattr(BASE, "repo", False):
        name = os.path.normpath(os.path.join(getattr(BASE, "dir", ""), target.split("#")[0])) if target.split("#")[0] else ""
        return ("/doc?name=" + quote(name) + ("#" + target.split("#", 1)[1] if "#" in target else "")) if name in DOCS else \
            ("#" + target.split("#", 1)[1] if target.startswith("#") else "#")
    if not re.match(r"^[\w./-]+$", target) or target.startswith("/") or ".." in target:
        return "#"
    base = getattr(BASE, "dir", "")
    return "/view?path=" + quote(os.path.normpath(os.path.join(base, target)))


def md_inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", lambda m: '<a href="%s">%s</a>' % (md_link(html.unescape(m.group(2))), m.group(1)), s)
    return s


def md_to_html(text: str) -> str:
    """A small Markdown subset: headings, paragraphs (wrapped lines joined), lists with wrapped items,
    numbered lists, fenced code (also inside list items), tables, inline code, bold and links."""
    out, lines, i = [], text.splitlines(), 0
    special = lambda l: (l.startswith("|") or re.match(r"^#{1,4}\s", l) or re.match(r"^\s*([-*]|\d+\.)\s+", l)
                         or l.strip().startswith("```"))

    def code_block(i):
        ind = len(lines[i]) - len(lines[i].lstrip())
        i += 1
        buf = []
        while i < len(lines) and not lines[i].strip().startswith("```"):
            buf.append(lines[i][ind:] if lines[i][:ind].strip() == "" else lines[i])
            i += 1
        return '<pre class="log">%s</pre>' % html.escape("\n".join(buf)), i + 1

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append('<div class="scroll"><table>')
            for j, r in enumerate(rows):
                if j == 1 and all(re.fullmatch(r":?-{2,}:?", c or "--") for c in r):
                    continue
                tag = "th" if j == 0 else "td"
                out.append("<tr>%s</tr>" % "".join("<%s>%s</%s>" % (tag, md_inline(c), tag) for c in r))
            out.append("</table></div>")
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", ln)
        if m:
            anchor = re.sub(r"[^a-z0-9 -]", "", m.group(2).lower()).strip().replace(" ", "-")
            out.append('<h%d id="%s">%s</h%d>' % (len(m.group(1)) + 1, anchor, md_inline(m.group(2)), len(m.group(1)) + 1))
            i += 1
        elif re.match(r"^\s*([-*]|\d+\.)\s+", ln):
            tag = "ol" if re.match(r"^\s*\d+\.", ln) else "ul"
            out.append("<%s>" % tag)
            while i < len(lines) and lines[i].strip():
                cur = lines[i]
                if re.match(r"^\s*([-*]|\d+\.)\s+", cur):
                    out.append("<li>%s" % md_inline(re.sub(r"^\s*([-*]|\d+\.)\s+", "", cur)))
                    i += 1
                elif cur.strip().startswith("```"):
                    block, i = code_block(i)
                    out.append(block)
                elif cur.startswith("  "):
                    out[-1] += " " + md_inline(cur.strip())
                    i += 1
                else:
                    break
            out.append("</%s>" % tag)
        elif ln.strip().startswith("```"):
            block, i = code_block(i)
            out.append(block)
        elif ln.strip():
            buf = [ln.strip()]
            i += 1
            while i < len(lines) and lines[i].strip() and not special(lines[i]):
                buf.append(lines[i].strip())
                i += 1
            out.append("<p>%s</p>" % md_inline(" ".join(buf)))
        else:
            i += 1
    return "\n".join(out)


def csv_to_html(text: str) -> str:
    import csv
    import io
    rows = list(csv.reader(io.StringIO(text)))
    out = ['<div class="scroll"><table>']
    for j, r in enumerate(rows[:2000]):
        tag = "th" if j == 0 else "td"
        out.append("<tr>%s</tr>" % "".join("<%s>%s</%s>" % (tag, html.escape(c), tag) for c in r))
    out.append("</table></div>")
    return "".join(out)


# --------------------------------------------------------------------------- pages
CSS = """
:root { color-scheme: light; --bg: #f6f6f4; --panel: #ffffff; --ink: #141414; --ink-2: #4f4e4a; --line: #dddcd6; --soft: #eeede8;
  --accent: #1f62b8; --accent-ink: #ffffff; --ok: #0b7a0b; --wait: #8a5a00; --wait-soft: #fff4dc; --err: #b42318; --err-soft: #fde8e6; --focus: #1f62b8; }
@media (prefers-color-scheme: dark) { :root { color-scheme: dark; --bg: #121211; --panel: #1b1b1a; --ink: #f2f2ef; --ink-2: #b9b8b0; --line: #34342f;
  --soft: #24241f; --accent: #5a9bea; --accent-ink: #0b0b0b; --ok: #4cc24c; --wait: #f0b54a; --wait-soft: #2e2615; --err: #ff8a80; --err-soft: #3a1b18; --focus: #8fbcf5; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
a { color: var(--accent); }
:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }
.skip { position: absolute; left: -999px; } .skip:focus { left: 8px; top: 8px; background: var(--panel); padding: 6px 10px; z-index: 9; }
header.bar { background: var(--panel); border-bottom: 1px solid var(--line); }
header.bar .in { max-width: 1100px; margin: 0 auto; padding: 10px 16px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px 20px; }
.brand { font-weight: 700; font-size: 18px; margin-right: auto; }
nav.tabs a { display: inline-block; padding: 6px 12px; border-radius: 8px; text-decoration: none; color: var(--ink); font-weight: 500; }
nav.tabs a[aria-current="page"] { background: var(--soft); }
main { max-width: 1100px; margin: 0 auto; padding: 20px 16px 80px; }
h1 { font-size: 26px; line-height: 1.25; margin: 4px 0 6px; }
h2 { font-size: 19px; margin: 0 0 10px; }
.lead { color: var(--ink-2); margin: 0 0 18px; max-width: 70ch; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 18px; margin: 14px 0; }
.card.wait { border-color: var(--wait); background: var(--wait-soft); }
.card.err { border-color: var(--err); background: var(--err-soft); }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px 18px; }
label { display: block; font-weight: 600; font-size: 14px; margin: 10px 0 4px; }
.hint { color: var(--ink-2); font-size: 14px; font-weight: 400; margin: 2px 0 0; }
input[type=text], input:not([type]), select, textarea { width: 100%; font: inherit; color: var(--ink); background: var(--panel); border: 1px solid var(--line);
  border-radius: 8px; padding: 8px 10px; }
textarea { min-height: 70px; resize: vertical; }
fieldset { border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px 14px; margin: 12px 0; }
legend { font-weight: 700; padding: 0 6px; }
.choice { display: flex; gap: 10px; align-items: flex-start; padding: 10px; border: 1px solid var(--line); border-radius: 10px; margin: 6px 0; font-weight: 400; cursor: pointer; }
.choice input { margin-top: 5px; }
.btn { display: inline-flex; align-items: center; gap: 6px; font: inherit; font-weight: 600; border: 1px solid var(--accent); background: var(--accent); color: var(--accent-ink);
  padding: 8px 14px; border-radius: 9px; cursor: pointer; text-decoration: none; }
.btn.ghost { background: transparent; color: var(--accent); }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.steps { list-style: none; padding: 0; margin: 0; }
.step { display: grid; grid-template-columns: 30px 1fr auto; gap: 10px; align-items: start; padding: 12px 0; border-top: 1px solid var(--line); }
.step:first-child { border-top: 0; }
.ic { width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; font-weight: 700; font-size: 14px; border: 2px solid var(--line); color: var(--ink-2); }
.done .ic { background: var(--ok); border-color: var(--ok); color: #fff; }
.next .ic { border-color: var(--accent); color: var(--accent); }
.step .name { font-weight: 600; }
.kind { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--ink-2); margin-left: 6px; }
.kind.human { color: var(--wait); }
.files { margin: 6px 0 0; padding-left: 18px; font-size: 14px; }
pre.log { background: #0f1113; color: #e6e6e6; padding: 12px; border-radius: 10px; max-height: 360px; overflow: auto; font: 13px/1.45 ui-monospace, Menlo, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
.pill { display: inline-block; font-size: 13px; padding: 2px 8px; border-radius: 99px; background: var(--soft); color: var(--ink-2); }
.pill.ok { color: var(--ok); } .pill.no { color: var(--err); } .pill.warn { color: var(--wait); }
.rq { display: grid; grid-template-columns: 90px 1fr; gap: 8px; margin-bottom: 8px; }
.fam { display: grid; grid-template-columns: 1fr 1.6fr 1.4fr 1.4fr; gap: 8px; align-items: end; padding: 8px 0; border-top: 1px dashed var(--line); }
.fam:first-of-type { border-top: 0; }
iframe.dash { width: 100%; height: 80vh; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; font-size: 14px; width: 100%; } th, td { border-bottom: 1px solid var(--line); padding: 5px 8px; text-align: left; vertical-align: top; }
code { overflow-wrap: anywhere; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .92em; background: var(--soft); padding: 1px 4px; border-radius: 4px; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
@media (max-width: 720px) { .fam { grid-template-columns: 1fr 1fr; } .rq { grid-template-columns: 1fr; } .step { grid-template-columns: 30px 1fr; } .step > .act { grid-column: 2; } }
"""

COMMON_JS = """
const TOKEN = document.querySelector('meta[name=council-token]').content;
async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Council-Token': TOKEN}, body: JSON.stringify(body)});
  const t = await r.text(); let j; try { j = JSON.parse(t); } catch (e) { j = {error: t}; }
  if (!r.ok && !j.error) j.error = 'HTTP ' + r.status;
  return j;
}
function esc(s) { return String(s ?? '').replace(/[&<>"]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[m]); }
function readFile(file) { return new Promise((ok, no) => { const fr = new FileReader(); fr.onload = () => ok(fr.result.split(',')[1] || ''); fr.onerror = no; fr.readAsDataURL(file); }); }
async function startDemo(btn) {
  if (btn) btn.disabled = true;
  const j = await api('/api/demo', {});
  if (j.error) { alert(j.error); if (btn) btn.disabled = false; return; }
  location.href = '/run';
}
"""


def page(title, active, body, script=""):
    cfg = STATE["config"]
    cur = ("Config: <code>%s</code>" % html.escape(os.path.relpath(cfg, REPO) if str(cfg).startswith(str(REPO)) else str(cfg))) if cfg else "No config yet"
    tabs = "".join('<a href="%s"%s>%s</a>' % (h, ' aria-current="page"' if active == n else "", n) for h, n in (("/", "Start"), ("/run", "Run"), ("/results", "Results")))
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<meta name=\"council-token\" content=\"%s\"><title>%s</title><style>%s</style></head><body>"
            "<a class=\"skip\" href=\"#main\">Skip to content</a>"
            "<header class=\"bar\"><div class=\"in\"><span class=\"brand\">Bounded AI council</span><nav class=\"tabs\" aria-label=\"Pages\">%s</nav>"
            "<span class=\"hint\">%s</span></div></header><main id=\"main\">%s</main><script>%s\n%s</script></body></html>") % (
        TOKEN, html.escape(title), CSS, tabs, cur, body, COMMON_JS, script)


START_BODY = """
<h1>Start a study</h1>
<p class="lead">Set up a run of the bounded AI council: your data, your research questions and the models that do the assembly work.
The researchers' steps (blind pass, codebook review, held-out coding, spot-check, low-reliability decisions) stay with you; the Run page stops and tells you when.</p>

<div class="card"><h2>New here? Try the demo first</h2>
<p class="hint">Runs the whole procedure, in Full mode, on 30 invented survey answers, with recorded replies instead of models. No key, no network, about ten seconds.</p>
<div class="row" style="margin-top:10px"><button class="btn" type="button" onclick="startDemo(this)">Try the demo</button></div></div>

<div class="card" id="connect"><h2>Connect your models</h2>
<p class="hint">Each model family is reached through its command-line tool (you log in once) or through an API key kept in an environment variable;
Full mode can also use the TypeSafe decision model. <a href="/doc?name=SETUP.md" target="_blank" rel="noopener">SETUP.md</a> explains every step for macOS, Linux and Windows,
what a run costs, and what to check before any data leaves this computer.</p>
<p class="hint">This check runs <code>council.py doctor</code> on the open config (or general checks if none is open). It never shows or stores a key: it only says whether the variable is set.
The app sees the environment of the terminal it was started from: set a key there, then restart the app.</p>
<div class="row" style="margin-top:10px"><button class="btn ghost" type="button" id="docbtn">Check my setup</button>
<button class="btn ghost" type="button" id="pingbtn">Test the connections (a few tokens each)</button></div>
<p class="hint" id="docmsg" role="status" aria-live="polite"></p><div id="docout"></div></div>

<div class="card"><h2>Open an existing config</h2>
<div class="row"><label class="sr" for="openpath">Path to a config file</label><input id="openpath" placeholder="config.yaml or examples/tiny/config.yaml" style="flex:1;min-width:220px">
<button class="btn ghost" type="button" id="openbtn">Open</button></div><p class="hint" id="openmsg" role="status"></p></div>

<form id="f" class="card" novalidate>
<h2>Or set up a new study</h2>
<label for="study_name">Study name</label><input id="study_name" name="study_name" value="my-study" required>
<p class="hint">Everything the run produces goes to <code>runs/&lt;study name&gt;/</code>.</p>

<fieldset><legend>Mode</legend>
<label class="choice"><input type="radio" name="mode" value="lite" checked><span><b>Lite</b>: three analysts propose codes, one reconciler merges them, three coders apply the approved codebook. Fewer model calls.</span></label>
<label class="choice"><input type="radio" name="mode" value="full"><span><b>Full</b>: Lite plus an adversary from another model family that challenges every role, and a calibrated yes/no decision model that screens codes and points the adversaries to likely errors.</span></label>
</fieldset>

<fieldset><legend>Your data</legend>
<p class="hint">A CSV file with a column <code>uid</code> (a unique id per unit) and a column <code>text</code>. Optional columns: <code>context</code>, <code>question</code>, <code>block</code>, <code>stratum</code>, <code>link</code>. De-identify it first.</p>
<label for="csvfile">Upload a CSV</label><input type="file" id="csvfile" accept=".csv,text/csv">
<label for="corpus_csv">or the path of a CSV on this computer</label><input id="corpus_csv" name="corpus_csv" placeholder="data/my_corpus.csv">
<p class="hint" id="csvmsg" role="status"></p>
<div class="grid2">
<div><label for="unit_name">One unit is a</label><input id="unit_name" name="unit_name" value="response"></div>
<div><label for="unit_name_plural">Plural</label><input id="unit_name_plural" name="unit_name_plural" value="responses"></div>
<div><label for="respondent_name">Written by a</label><input id="respondent_name" name="respondent_name" value="respondent"></div>
<div><label for="respondent_name_plural">Plural</label><input id="respondent_name_plural" name="respondent_name_plural" value="respondents"></div>
</div>
<label for="corpus_description">Describe the data in one or two sentences (the analysts read this)</label>
<textarea id="corpus_description" name="corpus_description">Answers of software developers to an open-ended survey question, one answer per unit, de-identified.</textarea>
</fieldset>

<fieldset><legend>Research questions</legend>
<div id="rqs"></div><button class="btn ghost" type="button" id="addrq">Add a question</button>
</fieldset>

<fieldset><legend>Model families</legend>
<p class="hint">Three analysts and three coders come from three different model families (A and coder 1 from the first, and so on); the first family also reconciles, the second challenges the reconciler.
For an API, give the <b>name</b> of the environment variable that holds the key (for example <code>GEMINI_API_KEY</code>), never the key itself.</p>
<div id="fams"></div>
</fieldset>

<fieldset id="dmset"><legend>Decision model (Full only)</legend>
<label class="choice"><input type="checkbox" id="dm_enabled" checked><span>Use a calibrated yes/no decision model (screening and leads)</span></label>
<div class="grid2"><div><label for="dm_backend">Decision model</label><select id="dm_backend">
<option value="typesafe">TypeSafe Jev (API)</option><option value="command">Any program with the same contract (command)</option><option value="manual">Manual (answered by hand or by an agent)</option></select></div>
<div id="dm_keybox"><label for="dm_key">Environment variable that holds its key</label><input id="dm_key" value="TYPESAFE_API_KEY"><p class="hint" id="dm_keystate"></p></div>
<div id="dm_cmdbox" hidden><label for="dm_command">Command</label><input id="dm_command" placeholder="python3 my_classifier.py"></div></div>
</fieldset>

<fieldset><legend>Data governance</legend>
<label for="data_governance">What leaves this computer, to which vendors, under which consent terms</label>
<textarea id="data_governance" name="data_governance" required placeholder="De-identified survey answers sent to Anthropic and OpenAI under ..."></textarea>
</fieldset>

<label for="config_path">Save as</label><input id="config_path" value="config.yaml">
<label class="choice"><input type="checkbox" id="overwrite"><span>Replace the file if it exists</span></label>
<div class="row" style="margin-top:12px"><button class="btn" type="submit">Save config.yaml</button><span class="hint" id="savemsg" role="status"></span></div>
<details style="margin-top:12px"><summary>Show the saved file</summary><pre class="log" id="yaml"></pre></details>
</form>
"""

START_JS = """
const BACKENDS = %s, KEYB = %s;
let rqn = 0;
function addRq(text, rationale) {
  rqn++; const d = document.createElement('div'); d.className = 'card'; d.style.margin = '8px 0';
  d.innerHTML = `<div class="rq"><div><label for="rqid${rqn}">Id</label><input id="rqid${rqn}" class="rqid" value="RQ${rqn}"></div>
  <div><label for="rqt${rqn}">Question</label><input id="rqt${rqn}" class="rqtext" value="${esc(text||'')}"></div></div>
  <label for="rqr${rqn}">What the question means (optional)</label><input id="rqr${rqn}" class="rqrat" value="${esc(rationale||'')}">
  <div class="row" style="margin-top:6px"><button type="button" class="btn ghost rm">Remove</button></div>`;
  d.querySelector('.rm').onclick = () => d.remove();
  document.getElementById('rqs').appendChild(d);
}
const DEF = [['claude','claude_cli','claude-opus-5',''],['gpt','codex_cli','gpt-5.6-terra',''],['gemini','gemini_api','','GEMINI_API_KEY']];
function addFam(i, f) {
  const d = document.createElement('div'); d.className = 'fam';
  d.innerHTML = `<div><label for="fn${i}">Family ${i+1}</label><input id="fn${i}" class="fname" value="${esc(f[0])}"></div>
  <div><label for="fb${i}">Backend</label><select id="fb${i}" class="fback">${BACKENDS.map(b => `<option value="${b[0]}" ${b[0]===f[1]?'selected':''}>${esc(b[1])}</option>`).join('')}</select></div>
  <div><label for="fm${i}">Model id</label><input id="fm${i}" class="fmodel" value="${esc(f[2])}"></div>
  <div class="keybox"><label for="fk${i}">Key variable name</label><input id="fk${i}" class="fkey" value="${esc(f[3])}"><p class="hint keystate"></p></div>`;
  document.getElementById('fams').appendChild(d);
  const sync = () => { const b = d.querySelector('.fback').value; const kb = d.querySelector('.keybox');
    kb.style.visibility = (b in KEYB) ? 'visible' : 'hidden'; if ((b in KEYB) && !d.querySelector('.fkey').value) d.querySelector('.fkey').value = KEYB[b]; checkEnv(); };
  d.querySelector('.fback').onchange = sync; d.querySelector('.fkey').oninput = checkEnv; sync();
}
async function checkEnv() {
  const els = [...document.querySelectorAll('.fam')].filter(d => d.querySelector('.keybox').style.visibility !== 'hidden');
  const names = els.map(d => d.querySelector('.fkey').value).concat([document.getElementById('dm_key').value]).filter(Boolean);
  const j = await api('/api/env?names=' + encodeURIComponent(names.join(',')));
  const show = (el, n) => { el.innerHTML = n ? (j[n] ? '<span class="pill ok">set in this environment</span>' : '<span class="pill no">not set: export it before starting the app</span>') : ''; };
  els.forEach(d => show(d.querySelector('.keystate'), d.querySelector('.fkey').value));
  show(document.getElementById('dm_keystate'), document.getElementById('dm_key').value);
}
function syncMode() {
  const full = document.querySelector('input[name=mode]:checked').value === 'full';
  document.getElementById('dmset').disabled = !full; document.getElementById('dmset').style.opacity = full ? 1 : .55;
  const b = document.getElementById('dm_backend').value;
  document.getElementById('dm_keybox').hidden = b !== 'typesafe'; document.getElementById('dm_cmdbox').hidden = b !== 'command';
}
document.querySelectorAll('input[name=mode]').forEach(r => r.onchange = syncMode);
document.getElementById('dm_backend').onchange = syncMode; document.getElementById('dm_key').oninput = checkEnv;
addRq('', ''); DEF.forEach((f, i) => addFam(i, f)); syncMode();
document.getElementById('addrq').onclick = () => addRq('', '');
document.getElementById('csvfile').onchange = async e => {
  const f = e.target.files[0]; if (!f) return; const msg = document.getElementById('csvmsg'); msg.textContent = 'Uploading…';
  const j = await api('/api/corpus', {filename: f.name, content: await readFile(f)});
  if (j.error) { msg.textContent = j.error; return; }
  document.getElementById('corpus_csv').value = j.path; msg.textContent = `Saved as ${j.path}: ${j.rows} units, columns ${j.columns.join(', ')}.`;
};
const DMARK = {pass: ['ok', 'PASS'], fail: ['no', 'FAIL'], warn: ['warn', 'WARN'], info: ['', 'info']};
async function runDoctor(ping) {
  const msg = document.getElementById('docmsg'), out = document.getElementById('docout');
  if (ping && !confirm('Send one tiny request to each model family and to the decision model? Each costs a few tokens.')) return;
  msg.textContent = ping ? 'Sending one tiny request to each…' : 'Checking…';
  const j = ping ? await api('/api/doctor', {ping: true}) : await api('/api/doctor');
  if (j.error) { msg.textContent = j.error; return; }
  msg.textContent = `${j.config ? 'Config ' + j.config : 'No config open: general checks'}. ${j.n_pass} passed, ${j.n_fail} failed, ${j.n_warn} warning(s).` +
    (j.n_fail ? ' Fix the FAIL lines, then check again.' : ' Ready.');
  let html = '', group = null;
  for (const it of j.items) {
    if (it.group !== group) { if (group !== null) html += '</ul>'; group = it.group; html += `<h3 style="margin:12px 0 4px;font-size:15px">${esc(group)}</h3><ul class="files" style="list-style:none;padding-left:0">`; }
    const [cls, lab] = DMARK[it.status] || ['', it.status];
    html += `<li style="margin:4px 0"><span class="pill ${cls}">${lab}</span> ${esc(it.name)}${it.detail ? ' <span class="hint">' + esc(it.detail) + '</span>' : ''}` +
      (it.fix && it.status !== 'pass' && it.status !== 'info' ? `<div class="hint" style="margin-left:52px">Fix: ${esc(it.fix)}</div>` : '') + '</li>';
  }
  out.innerHTML = html + (group !== null ? '</ul>' : '');
}
document.getElementById('docbtn').onclick = () => runDoctor(false);
document.getElementById('pingbtn').onclick = () => runDoctor(true);
document.getElementById('openbtn').onclick = async () => {
  const j = await api('/api/open', {path: document.getElementById('openpath').value});
  document.getElementById('openmsg').textContent = j.error || 'Opened. Go to the Run page.'; if (!j.error) location.href = '/run';
};
document.getElementById('f').onsubmit = async e => {
  e.preventDefault(); const msg = document.getElementById('savemsg'); msg.textContent = 'Saving…';
  const v = id => document.getElementById(id).value;
  const body = {study_name: v('study_name'), mode: document.querySelector('input[name=mode]:checked').value, corpus_csv: v('corpus_csv'),
    unit_name: v('unit_name'), unit_name_plural: v('unit_name_plural'), respondent_name: v('respondent_name'), respondent_name_plural: v('respondent_name_plural'),
    corpus_description: v('corpus_description'), data_governance: v('data_governance'),
    rqs: [...document.querySelectorAll('#rqs .card')].map(d => ({id: d.querySelector('.rqid').value, text: d.querySelector('.rqtext').value, rationale: d.querySelector('.rqrat').value})),
    families: [...document.querySelectorAll('.fam')].map(d => ({name: d.querySelector('.fname').value, backend: d.querySelector('.fback').value, model: d.querySelector('.fmodel').value,
      api_key_env: d.querySelector('.keybox').style.visibility === 'hidden' ? '' : d.querySelector('.fkey').value})),
    decision_model: {enabled: document.getElementById('dm_enabled').checked, backend: v('dm_backend'), api_key_env: v('dm_key'), command: v('dm_command')},
    config_path: v('config_path'), overwrite: document.getElementById('overwrite').checked};
  if (!body.data_governance.trim()) { msg.textContent = 'Say what leaves this computer, to which vendors, under which terms (data governance).'; document.getElementById('data_governance').focus(); return; }
  const j = await api('/api/config', body);
  if (j.error) { msg.textContent = j.error; return; }
  document.getElementById('yaml').textContent = j.yaml;
  msg.innerHTML = `Saved <code>${esc(j.path)}</code>. ${j.errors.length ? 'Fix: ' + esc(j.errors.join('; ')) : 'The config check passed.'} <a href="#connect">Check your models</a> &middot; <a href="/run">Go to Run</a>`;
  runDoctor(false);
};
""" % (json.dumps(BACKENDS), json.dumps(KEY_BACKENDS))

RUN_BODY = """
<h1>Run</h1>
<p class="lead">Run each stage in order. Stages marked <b>researchers</b> are yours: the app prepares the packet, then waits until you put back what the researchers return.</p>
<div id="top"></div>
<div class="card"><h2>Stages</h2><ol class="steps" id="steps"><li>Loading…</li></ol></div>
<div class="card" id="logcard"><h2 id="logtitle">Log</h2><p class="hint" id="jobstate" role="status" aria-live="polite">Nothing running.</p><pre class="log" id="log" tabindex="0" aria-label="Command output"></pre></div>
"""

RUN_JS = """
let last = null, polling = null;
const KIND = {program: 'program', model: 'models', human: 'researchers'};
function fileLink(f) { return `<a href="/view?path=${encodeURIComponent(f)}" target="_blank" rel="noopener">${esc(f)}</a>`; }
function render(s) {
  const top = document.getElementById('top'), ol = document.getElementById('steps');
  if (s.error) { top.innerHTML = `<div class="card err"><h2>No run to show</h2><p>${esc(s.error)}</p><div class="row"><a class="btn ghost" href="/">Go to Start</a><button class="btn" type="button" onclick="startDemo(this)">Try the demo</button></div></div>`; ol.innerHTML = ''; return; }
  let t = `<div class="card"><div class="row"><span class="pill">${esc(s.mode)} mode</span><span class="hint">workspace <code>${esc(s.workspace)}</code></span></div>`;
  if (s.errors.length) t += `<div class="card err"><b>Fix the config first:</b><ul>${s.errors.map(e => `<li>${esc(e)}</li>`).join('')}</ul></div>`;
  if (s.warnings.length) t += `<p class="hint">Warnings: ${s.warnings.map(esc).join('; ')}</p>`;
  if (s.manual_waiting.length) t += `<div class="card wait"><h2>Prompts are waiting for answers</h2><p>This config uses the <code>manual</code> backend: ${s.manual_waiting.length} prompt(s) in <code>manual/</code> need a reply file next to each (<code>&lt;name&gt;.reply.json</code>). Answer them, then run the same stage again.</p></div>`;
  if (!s.next) t += `<div class="card" style="border-color:var(--ok)"><h2>Every stage is done</h2><p>RESULTS.md and the results dashboard are ready.</p><a class="btn" href="/results">See the results</a></div>`;
  top.innerHTML = t + '</div>';
  ol.innerHTML = s.steps.map(st => {
    const isNext = st.id === s.next, cls = st.done ? 'done' : (isNext ? 'next' : '');
    let extra = '';
    if (st.kind === 'human' && (isNext || st.done || st.upload)) {
      const files = st.files.filter(Boolean);
      const open = isNext || !st.done;
      extra = `<details ${open ? 'open' : ''} style="margin-top:4px"><summary class="hint">${isNext ? 'Waiting for the researchers' : st.done ? 'Packet and returned files' : 'What the researchers do'}</summary>
        <div class="card ${isNext ? 'wait' : ''}" style="margin:8px 0 0">
        <b>${isNext ? 'Waiting for the researchers' : 'Researchers'}</b>${st.note ? `<p style="margin:4px 0">${esc(st.note)}</p>` : ''}
        ${files.length ? `<ul class="files">${files.map(f => `<li>${fileLink(f)}</li>`).join('')}</ul>` : ''}
        ${st.upload ? `<label for="up_${st.id}">${esc(st.upload.label)}</label><div class="row"><input type="file" id="up_${st.id}" data-dest="${esc(st.upload.dest)}" ${st.upload.dest.endsWith('/') ? 'multiple' : ''}>
          <span class="hint" id="upmsg_${st.id}" role="status"></span></div><p class="hint">Saved to <code>${esc(st.upload.dest)}</code> in the workspace.</p>` : ''}
      </div></details>`;
    } else if (st.note && isNext) extra = `<p class="hint">${esc(st.note)}</p>`;
    if (st.kind !== 'human' && st.files.length && st.done) extra += `<ul class="files">${st.files.map(f => `<li>${fileLink(f)}</li>`).join('')}</ul>`;
    return `<li class="step ${cls}"><span class="ic" aria-hidden="true">${st.done ? '&#10003;' : (isNext ? '&rarr;' : '')}</span>
      <div><span class="name">${esc(st.name)}</span><span class="kind ${st.kind}">${KIND[st.kind] || st.kind}</span>
      <span class="sr">${st.done ? 'done' : (isNext ? 'next step' : 'not done')}</span>${extra}</div>
      <div class="act">${st.run ? `<button class="btn ${isNext ? '' : 'ghost'}" type="button" data-step="${st.id}" ${(last && last.running) ? 'disabled' : ''}>${st.done ? 'Run again' : 'Run'}</button>` : ''}</div></li>`;
  }).join('');
  ol.querySelectorAll('button[data-step]').forEach(b => b.onclick = () => runStep(b.dataset.step));
  ol.querySelectorAll('input[type=file][data-dest]').forEach(inp => inp.onchange = () => upload(inp));
}
async function refresh() { render(await api('/api/status')); }
async function upload(inp) {
  const msg = document.getElementById('upmsg_' + inp.id.slice(3)); msg.textContent = 'Saving…';
  for (const f of inp.files) {
    const j = await api('/api/upload', {dest: inp.dataset.dest, filename: f.name, content: await readFile(f)});
    if (j.error) { msg.textContent = j.error; return; }
  }
  msg.textContent = `Saved ${inp.files.length} file(s).`; refresh();
}
async function runStep(id) {
  const j = await api('/api/run', {step: id});
  if (j.error) { alert(j.error); return; }
  document.getElementById('logcard').scrollIntoView({behavior: 'smooth'}); poll();
}
async function poll() {
  clearTimeout(polling);
  const j = await api('/api/job'); last = j;
  const log = document.getElementById('log'), st = document.getElementById('jobstate');
  if (j.id) {
    document.getElementById('logtitle').textContent = 'Log: ' + j.label;
    const atEnd = log.scrollTop + log.clientHeight >= log.scrollHeight - 8;
    log.textContent = j.log.join('\\n'); if (atEnd) log.scrollTop = log.scrollHeight;
    st.textContent = j.running ? 'Running…' : (j.exit === 0 ? 'Finished.' : j.exit === 3 ? 'Stopped: prompts are waiting for manual answers (see above).' : 'Stopped with an error (exit ' + j.exit + '). Read the last lines of the log.');
  }
  if (j.running) { polling = setTimeout(poll, 800); document.querySelectorAll('button[data-step]').forEach(b => b.disabled = true); }
  else refresh();
}
refresh(); poll();
"""


def results_body():
    ws = workspace()
    if not ws:
        return "<h1>Results</h1><div class=\"card err\"><p>No config yet. Start on the Start page or try the demo.</p></div>"
    links = [(p, n) for p, n in (("RESULTS.md", "RESULTS.md, the full report"), ("results/LJA/reliability_report.md", "Reliability report (Full)"),
                                  ("results/L/reliability_report.md", "Reliability report (Lite coding)"),
                                  ("human/02_author_review/codebook_review.html", "Author review dashboard"), ("results/costs.csv", "Cost table"))
             if (ws / p).exists()]
    lk = " &middot; ".join('<a href="/view?path=%s" target="_blank" rel="noopener">%s</a>' % (quote(p), html.escape(n)) for p, n in links)
    if not (ws / "dashboard.html").exists():
        return ("<h1>Results</h1><div class=\"card\"><p>No results dashboard yet. It is written after consensus (Stage 4), and again by the report step.</p>"
                "<p>%s</p><a class=\"btn\" href=\"/run\">Go to Run</a></div>" % lk)
    return ("<h1>Results</h1><p class=\"lead\">%s &middot; <a href=\"/ws/dashboard.html\" target=\"_blank\" rel=\"noopener\">Open the dashboard in its own tab</a></p>"
            "<iframe class=\"dash\" src=\"/ws/dashboard.html\" title=\"Results dashboard\"></iframe>" % lk)


# --------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "council-app"

    def log_message(self, fmt, *args):
        pass

    def local_host(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]")
        return host in ("127.0.0.1", "localhost", "::1")

    def send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def js(self, obj, code=200):
        self.send(code, json.dumps(obj), "application/json")

    def do_GET(self):
        if not self.local_host():
            return self.send(403, "forbidden")
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/":
            return self.send(200, page("Start a study", "Start", START_BODY, START_JS))
        if u.path == "/run":
            return self.send(200, page("Run", "Run", RUN_BODY, RUN_JS))
        if u.path == "/results":
            return self.send(200, page("Results", "Results", results_body()))
        if u.path == "/api/status":
            return self.js(status())
        if u.path == "/api/doctor":
            return self.js(doctor_checks(False))
        if u.path == "/doc":
            name = os.path.normpath(q.get("name", ["SETUP.md"])[0])
            if name not in DOCS or not (REPO / name).is_file():
                return self.send(404, page("Not found", "", "<h1>Not found</h1>"))
            BASE.repo, BASE.dir = True, os.path.dirname(name)
            try:
                body = md_to_html((REPO / name).read_text(encoding="utf-8"))
            finally:
                BASE.repo = False
            return self.send(200, page(name, "", "<p class=\"hint\"><code>%s</code></p>%s" % (html.escape(name), body)))
        if u.path == "/api/job":
            with JOB_LOCK:
                return self.js({k: JOB[k] for k in ("id", "running", "step", "label", "log", "exit")})
        if u.path == "/api/env":
            names = [n for n in (q.get("names", [""])[0]).split(",") if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n)]
            return self.js({n: bool(os.environ.get(n)) for n in names})
        if u.path.startswith("/ws/") or u.path == "/view":
            ws = workspace()
            rel = u.path[4:] if u.path.startswith("/ws/") else q.get("path", [""])[0]
            f = inside(ws, rel) if ws else None
            if not f or not f.is_file():
                return self.send(404, page("Not found", "", "<h1>Not found</h1><p>%s</p>" % html.escape(rel)))
            if u.path == "/view" and f.suffix in (".md", ".csv", ".json", ".txt"):
                text = f.read_text(encoding="utf-8", errors="replace")
                BASE.dir = os.path.dirname(rel)
                body = md_to_html(text) if f.suffix == ".md" else csv_to_html(text) if f.suffix == ".csv" else "<pre class=\"log\">%s</pre>" % html.escape(text)
                return self.send(200, page(f.name, "", "<p class=\"hint\"><code>%s</code> &middot; <a href=\"/ws/%s\">raw file</a></p>%s" % (
                    html.escape(rel), quote(rel), body)))
            if u.path == "/view":
                return self.send(302, b"", extra={"Location": "/ws/" + quote(rel)})
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/json",):
                ctype += "; charset=utf-8"
            if f.name.endswith(".md"):
                ctype = "text/plain; charset=utf-8"
            return self.send(200, f.read_bytes(), ctype)
        return self.send(404, page("Not found", "", "<h1>Not found</h1>"))

    def do_POST(self):
        if not self.local_host() or self.headers.get("X-Council-Token") != TOKEN:
            return self.js({"error": "forbidden: reload the page"}, 403)
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD * 1.4:
            return self.js({"error": "too large"}, 413)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self.js({"error": "bad request"}, 400)
        u = urlparse(self.path).path
        try:
            return {"/api/run": self.api_run, "/api/upload": self.api_upload, "/api/config": self.api_config, "/api/corpus": self.api_corpus,
                    "/api/open": self.api_open, "/api/demo": self.api_demo,
                    "/api/doctor": lambda b: self.js(doctor_checks(bool(b.get("ping"))))}.get(u, lambda b: self.js({"error": "unknown"}, 404))(body)
        except (ValueError, SystemExit) as e:
            return self.js({"error": str(e)}, 400)

    def api_run(self, b):
        s = status()
        if s.get("error"):
            return self.js({"error": s["error"]})
        st = next((x for x in s["steps"] if x["id"] == b.get("step") and x.get("run")), None)
        if not st:
            return self.js({"error": "unknown step"})
        script, args = st["run"][0], st["run"][1:]
        if script not in ("council.py", "run.py", "human.py"):
            return self.js({"error": "refused"})
        if not run_job(st["name"], py(script, "--config", str(STATE["config"]), *args), step=st["id"]):
            return self.js({"error": "another command is still running"})
        return self.js({"ok": True})

    def api_demo(self, b):
        STATE["config"] = DEMO_CONFIG
        if not run_job("Try the demo (offline replay)", py("demo.py"), step="demo"):
            return self.js({"error": "another command is still running"})
        return self.js({"ok": True})

    def api_upload(self, b):
        s = status()
        ws = workspace()
        allowed = {x["upload"]["dest"] for x in s.get("steps", []) if x.get("upload")}
        dest = b.get("dest") or ""
        if dest not in allowed or not ws:
            return self.js({"error": "this file cannot be placed there"})
        data = base64.b64decode(b.get("content") or "")
        if len(data) > MAX_UPLOAD:
            return self.js({"error": "file too large"})
        if dest.endswith("/"):
            name = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(b.get("filename") or "file").name) or "file"
            target = inside(ws, dest + name)
        else:
            target = inside(ws, dest)
        if not target:
            return self.js({"error": "bad destination"})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return self.js({"ok": True, "path": str(target.relative_to(ws))})

    def api_corpus(self, b):
        import csv
        import io
        data = base64.b64decode(b.get("content") or "")
        if len(data) > MAX_UPLOAD:
            return self.js({"error": "file too large"})
        text = data.decode("utf-8-sig", errors="replace")
        rows = list(csv.DictReader(io.StringIO(text)))
        cols = list(rows[0].keys()) if rows else []
        if "uid" not in cols or "text" not in cols:
            return self.js({"error": "the CSV needs columns uid and text; found: %s" % ", ".join(c for c in cols if c) or "none"})
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(b.get("filename") or "corpus.csv").name)
        if not name.lower().endswith(".csv"):
            name += ".csv"
        d = REPO / "data"
        d.mkdir(exist_ok=True)
        (d / name).write_bytes(data)
        return self.js({"ok": True, "path": "data/" + name, "rows": len(rows), "columns": [c for c in cols if c]})

    def api_config(self, b):
        p = Path(b.get("config_path") or "config.yaml").expanduser()
        p = p if p.is_absolute() else REPO / p
        if p.suffix not in (".yaml", ".yml"):
            raise ValueError("save the config as a .yaml file")
        if p.exists() and not b.get("overwrite"):
            raise ValueError("%s exists; tick 'Replace the file if it exists' or choose another name" % p.name)
        corpus = Path(b.get("corpus_csv") or "")
        b["corpus_csv"] = str(corpus if corpus.is_absolute() else REPO / corpus) if str(corpus).strip() else ""
        text = build_config(b, p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        cfg = C.load(p)
        errs, _ = cfg.check()
        STATE["config"] = p
        return self.js({"ok": True, "path": os.path.relpath(p, REPO), "yaml": text, "errors": errs})

    def api_open(self, b):
        p = Path(b.get("path") or "").expanduser()
        p = p if p.is_absolute() else REPO / p
        if not p.is_file():
            raise ValueError("no file %s" % p)
        C.load(p)
        STATE["config"] = p
        return self.js({"ok": True})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--config", help="open this config at start (default: config.yaml in the repository, if present)")
    ap.add_argument("--open", action="store_true", help="open the address in your web browser")
    a = ap.parse_args(argv)
    STATE["config"] = Path(a.config).resolve() if a.config else initial_config()
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    except OSError as e:
        raise SystemExit("cannot listen on 127.0.0.1:%d (%s); try --port %d" % (a.port, e, a.port + 1))
    url = "http://127.0.0.1:%d/" % a.port
    print("Council app running at %s  (only this computer can reach it; Ctrl+C to stop)" % url, flush=True)
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
