#!/usr/bin/env python3
"""
Configuration for the council pipeline.

A run is described by one file, config.yaml (or config.json), next to which every relative path
is resolved. `load(path)` returns a Config object with defaults filled in and the roster derived
(which family critiques which analyst or coder). Nothing in the pipeline reads a path, a model id
or a threshold from anywhere else.

YAML is read with PyYAML when it is installed; otherwise a small built-in reader handles the
subset the example configs use (block mappings and lists, flow lists and mappings, quoted and
plain scalars, `|` and `>` block scalars, comments). JSON is always supported.

Standard library only.
"""
from __future__ import annotations

import json
import re
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent
REPO = PIPELINE.parent
PROMPTS = REPO / "prompts"

# --------------------------------------------------------------------------- defaults
DEFAULTS = {
    "mode": "lite",
    "workspace": "runs/study",
    "study": {
        "corpus_csv": "data/corpus.csv",
        "unit_name": "response",
        "unit_name_plural": "responses",
        "respondent_name": "respondent",
        "respondent_name_plural": "respondents",
        "corpus_description": "",
        "scope_rule": "Code only what a respondent states in the unit.",
        "research_questions": [],
    },
    # The method names three issue codes (Stage 4). A study may add its own.
    "issue_codes": OrderedDict([
        ("ISSUE_WRONG_FIELD", "The text answers another field or question and cannot be coded as supplied."),
        ("ISSUE_BACK_REFERENCE", "The unit only refers to missing material (for example 'same as above') and lacks enough content."),
        ("ISSUE_NON_RESPONSE", "Blank, 'N/A', 'no comment', an unreadable fragment, or another non-answer."),
    ]),
    "roles": {
        "analysts": OrderedDict([("A", "claude"), ("B", "gpt"), ("C", "gemini")]),
        "reconciler": "claude",
        "reconciliation_adversary": "gpt",
        "coders": OrderedDict([("1", "claude"), ("2", "gpt"), ("3", "gemini")]),
        # Figure 2 rotation: A is critiqued by C's family, B by A's, C by B's (same for coders 1, 2, 3).
        "adversaries": None,
        "coding_adversaries": None,
    },
    "models": {},
    "reasoning": {
        # Discovery and reconciliation run at each model's default reasoning; every other call is reduced.
        "default_stages": ["discovery", "discovery-repair", "discovery-answer", "reconcile", "reconcile-answer"],
        "reduced_effort": "low",
    },
    "decision_model": {
        "enabled": True,
        "backend": "typesafe",              # typesafe | command
        "endpoint": "https://api.typesafe.ai/v1/systemone",
        "model": "jev-latest",
        "api_key_env": "TYPESAFE_API_KEY",  # the name of the environment variable, never the key
        "command": None,                    # backend: command -> a program that reads a request on stdin
        "workers": 8,
    },
    "thresholds": {
        "support_floor": 3,
        "min_quotes": 3,
        "consensus": 2,
        "alpha_drop": 0.67,
        "alpha_high": 0.80,
        "grounding_lead_below": 0.5,
        "omission_lead_at_or_above": 0.8,
        "screening_tau": 0.10,
        "screening_top_k": 5,
        "screening_audit_share": 0.05,
        "coding_lead_assigned_below": 0.2,
        "coding_lead_unassigned_at_or_above": 0.8,
        "max_label_words": 14,
    },
    "batch_size": 25,
    "discovery_block_size": 0,
    "max_repairs": 2,
    "workers": 6,
    "reconciliation": {"groups_per_rq": [5, 15], "run_lite_baseline_in_full": True},
    "splits": {
        "seed": 20260930,
        "development_share": 0.25,
        "blind_pass_min": 50,
        "blind_pass_share": 0.10,
        "blind_pass_max": 200,
        "held_out_min": 50,
        "strata_columns": ["question", "block", "stratum"],
    },
    "reliability": {"units": "evaluation"},
    "spot_check": {"random_sample": 50, "seed": 20260930},
    "prices": {},
    "data_governance": "",
}

FULL_ONLY = ("adversaries", "decision model")
BACKENDS = ("claude_cli", "codex_cli", "anthropic_api", "openai_api", "gemini_api", "command", "manual", "replay")
DM_BACKENDS = ("typesafe", "command", "manual", "replay")


# --------------------------------------------------------------------------- tiny YAML reader
class YamlError(ValueError):
    pass


def _strip_comment(line: str) -> str:
    out, q = [], None
    for i, ch in enumerate(line):
        if q:
            out.append(ch)
            if ch == q:
                q = None
            continue
        if ch in "\"'":
            q = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(s: str):
    s = s.strip()
    if s == "" or s in ("~", "null", "Null", "NULL"):
        return None
    if s[0] in "\"'" and s[-1] == s[0] and len(s) >= 2:
        body = s[1:-1]
        if s[0] == '"':
            return json.loads(s) if "\\" in body else body
        return body.replace("''", "'")
    if s in ("true", "True", "TRUE", "yes", "on"):
        return True
    if s in ("false", "False", "FALSE", "no", "off"):
        return False
    if re.fullmatch(r"[-+]?\d+", s):
        return int(s)
    if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?", s):
        return float(s)
    if s[0] in "[{":
        val, end = _flow(s, 0)
        if s[end:].strip():
            raise YamlError("trailing text after flow value: %r" % s)
        return val
    return s


def _flow(s: str, i: int):
    """Parse a flow list or mapping starting at s[i]; return (value, index after it)."""
    def ws(j):
        while j < len(s) and s[j] in " \t":
            j += 1
        return j

    def atom(j, stops):
        j = ws(j)
        if s[j] in "[{":
            return _flow(s, j)
        if s[j] in "\"'":
            q = s[j]
            k = j + 1
            while k < len(s):
                if s[k] == q and not (q == '"' and s[k - 1] == "\\"):
                    break
                k += 1
            return _scalar(s[j:k + 1]), k + 1
        k = j
        while k < len(s) and s[k] not in stops:
            k += 1
        return _scalar(s[j:k]), k

    if s[i] == "[":
        out, j = [], ws(i + 1)
        if s[j] == "]":
            return out, j + 1
        while True:
            v, j = atom(j, ",]")
            out.append(v)
            j = ws(j)
            if s[j] == ",":
                j += 1
                continue
            if s[j] == "]":
                return out, j + 1
            raise YamlError("bad flow list: %r" % s)
    out, j = OrderedDict(), ws(i + 1)
    if s[j] == "}":
        return out, j + 1
    while True:
        k, j = atom(j, ":")
        j = ws(j)
        if s[j] != ":":
            raise YamlError("bad flow mapping: %r" % s)
        v, j = atom(j + 1, ",}")
        out[str(k)] = v
        j = ws(j)
        if s[j] == ",":
            j += 1
            continue
        if s[j] == "}":
            return out, j + 1
        raise YamlError("bad flow mapping: %r" % s)


def _split_key(text: str):
    """'key: value' -> (key, value) or None when the line is not a mapping entry."""
    if text[:1] in "\"'":
        q = text[0]
        end = text.find(q, 1)
        if end > 0 and text[end + 1:end + 2] == ":":
            return text[1:end], text[end + 2:]
        return None
    m = re.match(r"([^:\[\]{}#,]+?):(\s|$)", text)
    if not m:
        return None
    return m.group(1).strip(), text[m.end() - (1 if m.group(2) else 0):]


def mini_yaml(text: str):
    raw = text.replace("\t", "    ").splitlines()
    lines = []          # (indent, content, raw_line)
    for ln in raw:
        if not ln.strip() or ln.lstrip().startswith("#") or ln.strip() == "---":
            lines.append(None)
            continue
        lines.append((len(ln) - len(ln.lstrip(" ")), _strip_comment(ln).strip(), ln))
    pos = [0]

    def skip():
        while pos[0] < len(lines) and lines[pos[0]] is None:
            pos[0] += 1

    def block_scalar(style, parent_indent):
        body = []
        ind = None
        while pos[0] < len(raw):
            ln = raw[pos[0]]
            if ln.strip():
                cur = len(ln) - len(ln.lstrip(" "))
                if cur <= parent_indent:
                    break
                ind = cur if ind is None else ind
                body.append(ln[ind:])
            else:
                body.append("")
            pos[0] += 1
        while body and body[-1] == "":
            body.pop()
        if style.startswith("|"):
            return "\n".join(body) + "\n"
        paras, cur = [], []
        for b in body:
            if b == "":
                paras.append(" ".join(cur))
                cur = []
            else:
                cur.append(b.strip())
        paras.append(" ".join(cur))
        return "\n".join(p for p in paras) + "\n"

    def value_after(rest, indent):
        rest = rest.strip()
        if rest in ("|", ">", "|-", ">-"):
            pos[0] += 1
            v = block_scalar(rest, indent)
            return v.rstrip("\n") if rest.endswith("-") else v
        pos[0] += 1
        if rest == "":
            skip()
            if pos[0] < len(lines) and lines[pos[0]][0] > indent:
                return parse(lines[pos[0]][0])
            if pos[0] < len(lines) and lines[pos[0]][0] == indent and lines[pos[0]][1].startswith("- "):
                return parse(indent)
            return None
        return _scalar(rest)

    def parse(indent):
        skip()
        if pos[0] >= len(lines):
            return None
        ind, content, _ = lines[pos[0]]
        if content.startswith("- ") or content == "-":
            out = []
            while True:
                skip()
                if pos[0] >= len(lines):
                    return out
                ind, content, _ = lines[pos[0]]
                if ind != indent or not (content.startswith("- ") or content == "-"):
                    return out
                item = content[1:].strip()
                kv = _split_key(item) if item else None
                if kv:
                    # a mapping that starts on the dash line
                    sub = indent + 2 + (len(content[1:]) - len(content[1:].lstrip(" ")) - 1)
                    lines[pos[0]] = (sub, item, lines[pos[0]][2])
                    out.append(parse(sub))
                elif item == "":
                    pos[0] += 1
                    skip()
                    out.append(parse(lines[pos[0]][0]) if pos[0] < len(lines) else None)
                else:
                    pos[0] += 1
                    out.append(_scalar(item))
        out = OrderedDict()
        while True:
            skip()
            if pos[0] >= len(lines):
                return out
            ind, content, rawl = lines[pos[0]]
            if ind < indent:
                return out
            if ind > indent:
                raise YamlError("unexpected indentation: %r" % rawl)
            kv = _split_key(content)
            if not kv:
                raise YamlError("expected 'key: value': %r" % rawl)
            k, rest = kv
            out[k] = value_after(rest, indent)

    result = parse(0)
    skip()
    if pos[0] < len(lines):
        raise YamlError("could not parse line: %r" % lines[pos[0]][2])
    return result


def read_config_file(path: Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    if str(path).endswith(".json"):
        return json.loads(text, object_pairs_hook=OrderedDict)
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except ImportError:
        return mini_yaml(text) or {}


# --------------------------------------------------------------------------- config object
def _merge(base, over):
    out = deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("issue_codes", "prices", "models"):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(s)) or "RQ"


class Config:
    def __init__(self, data: dict, path: Path | None):
        self.path = Path(path).resolve() if path else None
        self.base = self.path.parent if self.path else Path.cwd()
        self.d = _merge(DEFAULTS, data)
        self.mode = str(self.d["mode"]).lower()
        if self.mode not in ("lite", "full"):
            raise SystemExit("config: mode must be 'lite' or 'full', got %r" % self.mode)
        self.study = self.d["study"]
        self.t = self.d["thresholds"]
        self.rqs = OrderedDict()
        for q in self.study.get("research_questions") or []:
            if isinstance(q, str):
                q = {"id": "RQ%d" % (len(self.rqs) + 1), "text": q}
            qid = str(q["id"])
            self.rqs[qid] = {"id": qid, "text": str(q["text"]).strip(), "rationale": str(q.get("rationale") or "").strip(),
                             "slug": str(q.get("slug") or slug(qid))}
        if len({v["slug"] for v in self.rqs.values()}) != len(self.rqs):
            raise SystemExit("config: research question slugs must be unique")
        self.issue_codes = OrderedDict((str(k), str(v)) for k, v in (self.d["issue_codes"] or {}).items())
        self._roster()

    # paths
    def resolve(self, p) -> Path:
        p = Path(str(p)).expanduser()
        return p if p.is_absolute() else (self.base / p)

    @property
    def workspace(self) -> Path:
        return self.resolve(self.d["workspace"])

    @property
    def corpus_csv(self) -> Path:
        return self.resolve(self.study["corpus_csv"])

    # roster
    def _roster(self):
        r = self.d["roles"]
        self.analysts = OrderedDict((str(k), str(v)) for k, v in r["analysts"].items())
        self.coders = OrderedDict((str(k), str(v)) for k, v in r["coders"].items())
        self.reconciler = str(r["reconciler"])
        self.recon_adversary = str(r.get("reconciliation_adversary") or "")

        def rotate(roles):
            keys = list(roles)
            return OrderedDict((k, roles[keys[i - 1]]) for i, k in enumerate(keys))  # A <- C, B <- A, C <- B

        self.analyst_adversary = OrderedDict((str(k), str(v)) for k, v in (r.get("adversaries") or rotate(self.analysts)).items())
        self.coder_adversary = OrderedDict((str(k), str(v)) for k, v in (r.get("coding_adversaries") or rotate(self.coders)).items())
        self.cross_family_pairs = [(a, b) for i, a in enumerate(self.coders) for b in list(self.coders)[i + 1:]
                                   if self.coders[a] != self.coders[b]]

    def family_model(self, family: str) -> dict:
        m = (self.d.get("models") or {}).get(family)
        if not m:
            raise SystemExit("config: no entry under `models` for family %r" % family)
        return m

    @property
    def full(self) -> bool:
        return self.mode == "full"

    @property
    def decision_model_on(self) -> bool:
        return self.full and bool(self.d["decision_model"].get("enabled"))

    def check(self) -> list[str]:
        """Problems that stop a run (errors) or deserve a line in the report (warnings)."""
        errs, warns = [], []
        if not self.rqs:
            errs.append("study.research_questions is empty")
        if not self.corpus_csv.exists():
            errs.append("corpus not found: %s" % self.corpus_csv)
        if len(self.analysts) != 3 or len(self.coders) != 3:
            errs.append("the procedure uses three analysts and three coders")
        fams = set(self.analysts.values()) | set(self.coders.values()) | {self.reconciler}
        if self.full:
            fams |= set(self.analyst_adversary.values()) | set(self.coder_adversary.values()) | {self.recon_adversary}
            for k, f in self.analysts.items():
                if self.analyst_adversary.get(k) == f:
                    errs.append("analyst %s and its adversary are both %s; the adversary must be another family" % (k, f))
            for k, f in self.coders.items():
                if self.coder_adversary.get(k) == f:
                    errs.append("coder %s and its adversary are both %s; the adversary must be another family" % (k, f))
            if not self.recon_adversary or self.recon_adversary == self.reconciler:
                errs.append("the reconciliation adversary must be another family than the reconciler")
        for f in sorted(fams):
            if f not in (self.d.get("models") or {}):
                errs.append("family %r is used by a role but has no entry under `models`" % f)
        if len(set(self.analysts.values())) < 3:
            warns.append("fewer than three families among the analysts; report the vendor caveat")
        if len(set(self.coders.values())) < 3:
            warns.append("two coders share a family; cross-family kappa is reported separately")
        bs = int(self.d["batch_size"])
        if not 20 <= bs <= 50:
            warns.append("batch_size %d is outside the 20 to 50 the method specifies" % bs)
        for issue in self.issue_codes:
            if not issue.startswith("ISSUE_"):
                errs.append("issue code %r must start with ISSUE_" % issue)
        for f, m in (self.d.get("models") or {}).items():
            b = (m or {}).get("backend", "claude_cli")
            if b not in BACKENDS:
                errs.append("models.%s.backend %r is not one of %s" % (f, b, ", ".join(BACKENDS)))
            if b == "replay" and not (m or {}).get("replay_dir"):
                errs.append("models.%s: backend replay needs `replay_dir`" % f)
            if "REPLACE" in str((m or {}).get("model", "")) or not (m or {}).get("model"):
                errs.append("models.%s.model is not set (it is %r); give the model id you use" % (f, (m or {}).get("model")))
            if (m or {}).get("api_key"):
                errs.append("models.%s holds `api_key`; put the key in an environment variable and name it in `api_key_env`" % f)
        if self.decision_model_on:
            dm = self.d["decision_model"]
            b = dm.get("backend", "typesafe")
            if b not in DM_BACKENDS:
                errs.append("decision_model.backend %r is not one of %s" % (b, ", ".join(DM_BACKENDS)))
            if b == "command" and not dm.get("command"):
                errs.append("decision_model.backend is command but decision_model.command is empty")
            if b == "replay" and not dm.get("replay_dir"):
                errs.append("decision_model: backend replay needs `replay_dir`")
        return errs, warns

    def summary(self) -> dict:
        return OrderedDict([
            ("mode", self.mode), ("workspace", str(self.workspace)), ("corpus_csv", str(self.corpus_csv)),
            ("research_questions", list(self.rqs.values())),
            ("analysts", self.analysts), ("analyst_adversaries", self.analyst_adversary if self.full else None),
            ("reconciler", self.reconciler), ("reconciliation_adversary", self.recon_adversary if self.full else None),
            ("coders", self.coders), ("coding_adversaries", self.coder_adversary if self.full else None),
            ("cross_family_coder_pairs", ["%s-%s" % p for p in self.cross_family_pairs]),
            ("models", {f: {k: v for k, v in (m or {}).items() if k != "api_key"} for f, m in (self.d.get("models") or {}).items()}),
            ("decision_model", {k: v for k, v in self.d["decision_model"].items()} if self.decision_model_on else None),
            ("thresholds", self.t), ("batch_size", self.d["batch_size"]),
            ("discovery_block_size", self.d["discovery_block_size"]), ("issue_codes", self.issue_codes),
            ("splits", self.d["splits"]), ("reliability", self.d["reliability"]),
            ("data_governance", self.d.get("data_governance", "")),
        ])


def load(path: str | Path | None = None) -> Config:
    if path is None:
        for cand in ("config.yaml", "config.yml", "config.json"):
            if Path(cand).exists():
                path = cand
                break
    if path is None:
        raise SystemExit("no config file: pass --config PATH (copy config.example.yaml to config.yaml)")
    return Config(read_config_file(Path(path)), Path(path))
