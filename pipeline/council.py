#!/usr/bin/env python3
"""
The deterministic stages of the bounded AI council procedure. This file never calls a model.

Every model step is a brief (rendered from ../prompts/*.md) plus the input files that role may see,
and a JSON file the answer is saved to. `run.py` sends briefs to models through `models.py`; an
agent or a person can also answer them by hand (see AGENTS.md). Everything else is here:

  prepare            copy the corpus into the workspace, fix unit order, write corpus.txt, blocks,
                     the development / evaluation split, the blind-pass and held-out samples, manifest
  discovery-briefs   one brief per analyst x research question (x block)
  merge-readings     merge an analyst's per-question readings into discovery/<stage>/analyst_<A>.json
  validate           provenance check of discovery files (and the adversaries' quarantined codes)
  apply-delta        v1 = v0 + an analyst's delta (Full)
  freeze             sha256 + read-only for the pre-adversary files (discovery v0, coding v0)
  reconcile-prepare  raw codes, overlap table and per-question reconciliation briefs (--cond lite|full)
  reconcile-apply    combine per-question plans; apply the support floor; candidate codebook
  approve            apply the author-review edit log -> codebooks/approved_codebook.json (closed)
  code-prepare       batches and coder / coding-adversary / coder-answer briefs
  consensus          Stage 5 for one coding condition (L, LJ, LJA): consensus, reliability, drop rule
  dashboard          <workspace>/dashboard.html, the results dashboard (also refreshed by consensus and report)
  status             what has been done in this workspace and the next step (--json for programs)
  export-replies     copy a manual run's replies to a folder the `replay` backend reads (offline demos, audits)
  refine             after the low-alpha decision: archive the coding round, write the next codebook
                     version with the refined definitions (dropped codes removed); then `run.py code`

Reporting commands (report, cost, heldout-score, retention, check-quotes, log-call) are in report.py
and reachable through this file as well.

Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
import sys
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import prompts as P  # noqa: E402
import reliability as R  # noqa: E402

LAYERS = ["semantic", "latent", "contrastive"]
UNCOVERED = R.UNCOVERED
REL_TYPES = {"equivalent", "broader_than", "narrower_than", "overlaps", "contrasts_with"}
REL_ALIAS = {"overlaps_with": "overlaps", "narrower": "narrower_than", "broader": "broader_than",
             "contrasts": "contrasts_with", "equivalent_to": "equivalent"}

cfg: C.Config = None   # set by init()
W: Path = None


def init(config_path=None) -> C.Config:
    global cfg, W
    cfg = C.load(config_path)
    W = cfg.workspace
    return cfg


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- io
def D(*parts) -> Path:
    p = W.joinpath(*parts)
    (p if not p.suffix else p.parent).mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: Path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not os.access(path, os.W_OK):
        os.chmod(path, 0o644)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)


def rj(path: Path, default=None):
    p = Path(path)
    return read_json(p) if p.exists() else ({} if default is None else default)


def read_csv(path: Path):
    csv.field_size_limit(10 ** 9)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------- corpus
def load_corpus() -> "OrderedDict[str, dict]":
    p = W / "data" / "corpus.csv"
    if not p.exists():
        raise SystemExit("no prepared corpus in %s; run `council.py prepare` first" % W)
    return OrderedDict((r["uid"], r) for r in read_csv(p))


def has_context(corpus) -> bool:
    return any((r.get("context") or "").strip() for r in corpus.values())


def unit_text_block(uid: str, r: dict) -> str:
    s = "[%s]\n%s" % (uid, r["text"].strip())
    if (r.get("context") or "").strip():
        s += "\nCONTEXT: %s" % r["context"].strip()
    return s


def splits() -> dict:
    return rj(W / "data" / "splits.json")


def blocks() -> list:
    b = rj(W / "data" / "blocks.json")
    return b.get("blocks") or [{"id": None, "units": list(load_corpus())}]


def proportional(units: list, strata: dict, n: int, rng: random.Random) -> list:
    """Draw n ids proportionally across strata (largest-remainder rounding)."""
    by = defaultdict(list)
    for u in units:
        by[strata.get(u, "all")].append(u)
    n = min(n, len(units))
    quota = {s: n * len(v) / len(units) for s, v in by.items()}
    take = {s: int(q) for s, q in quota.items()}
    for s in sorted(quota, key=lambda s: quota[s] - take[s], reverse=True)[: n - sum(take.values())]:
        take[s] += 1
    out = []
    for s in sorted(by):
        out += rng.sample(sorted(by[s]), min(take[s], len(by[s])))
    pos = {u: i for i, u in enumerate(units)}
    return sorted(out, key=pos.get)


def cmd_prepare(args):
    errs, warns = cfg.check()
    for w in warns:
        print("   warning: %s" % w)
    if errs:
        for e in errs:
            print("   ERROR: %s" % e)
        raise SystemExit("config check failed")
    rows = read_csv(cfg.corpus_csv)
    if not rows or "uid" not in rows[0] or "text" not in rows[0]:
        raise SystemExit("the corpus CSV needs columns `uid` and `text` (optional: context, question, block, stratum, link)")
    seen, out = set(), []
    for r in rows:
        uid = (r.get("uid") or "").strip()
        if not uid or uid in seen:
            raise SystemExit("unit ids must be present and unique; problem at %r" % uid)
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", uid):
            raise SystemExit("unit id %r: use letters, digits, _ . : - only" % uid)
        seen.add(uid)
        r = OrderedDict((k, (v or "").replace("\r\n", "\n").strip() if isinstance(v, str) else v) for k, v in r.items() if k)
        r["uid"] = uid
        out.append(r)
    cols = ["uid", "text"] + (["context"] if any(r.get("context") for r in out) else []) + \
           [c for c in out[0].keys() if c not in ("uid", "text", "context")]
    txt = "\n\n".join(unit_text_block(r["uid"], r) for r in out) + "\n"
    sha = hashlib.sha256(txt.encode()).hexdigest()
    old = rj(W / "manifest.json")
    if old and old.get("corpus_txt_sha256") not in (None, sha) and not args.force:
        raise SystemExit("the workspace already holds a different corpus (sha256 %s). Unit ids and order must stay fixed "
                         "across analysts and coders; use a new workspace or pass --force." % old["corpus_txt_sha256"][:12])
    R.write_csv(D("data", "corpus.csv"), out, cols)
    D("data", "corpus.txt").write_text(txt, encoding="utf-8")

    # blocks: only when the corpus exceeds a context window (discovery_block_size > 0)
    bs = int(cfg.d["discovery_block_size"] or 0)
    uids = [r["uid"] for r in out]
    blist = []
    if bs and bs < len(uids):
        for i in range(0, len(uids), bs):
            b = {"id": "B%d" % (len(blist) + 1), "units": uids[i:i + bs]}
            D("data", "blocks", "%s.txt" % b["id"]).write_text(
                "\n\n".join(unit_text_block(u, out[uids.index(u)]) for u in b["units"]) + "\n", encoding="utf-8")
            blist.append(b)
    write_json(D("data", "blocks.json"), {"block_size": bs, "blocks": blist})

    # splits: development (examples, blind pass) and evaluation (reliability, held-out sample)
    sp = cfg.d["splits"]
    rng = random.Random(int(sp["seed"]))
    by_uid = {r["uid"]: r for r in out}
    block_of = {u: b["id"] for b in blist for u in b["units"]}
    strata = {}
    for u in uids:
        parts = [str(by_uid[u].get(c) or "") for c in sp["strata_columns"] if c != "block" and by_uid[u].get(c)]
        if "block" in sp["strata_columns"] and block_of.get(u):
            parts.append(block_of[u])
        strata[u] = "/".join(parts) or "all"
    dev = proportional(uids, strata, round(float(sp["development_share"]) * len(uids)), rng)
    dset = set(dev)
    ev = [u for u in uids if u not in dset]
    n_blind = max(int(sp["blind_pass_min"]), min(int(sp["blind_pass_max"]), math.ceil(float(sp["blind_pass_share"]) * len(uids))))
    pool, note = dev, "drawn from the development units"
    if len(dev) < n_blind:
        pool, note = uids, "drawn from the whole corpus (fewer development units than the blind-pass size)"
    blind = proportional(pool, strata, n_blind, rng)
    held = proportional(ev, strata, int(sp["held_out_min"]), rng)
    if len(held) < int(sp["held_out_min"]):
        warns.append("held-out sample has %d units, fewer than %s" % (len(held), sp["held_out_min"]))
    write_json(D("data", "splits.json"), OrderedDict([
        ("seed", sp["seed"]), ("corpus_txt_sha256", sha), ("strata", strata),
        ("development", dev), ("evaluation", ev), ("blind_pass", blind), ("blind_pass_note", note), ("held_out", held)]))
    manifest = OrderedDict([
        ("procedure", "bounded AI council, %s" % cfg.mode.capitalize()), ("prepared_at", now()),
        ("config", str(cfg.path)), ("corpus_source", str(cfg.corpus_csv)), ("n_units", len(uids)),
        ("has_context", any(r.get("context") for r in out)), ("corpus_txt_sha256", sha),
        ("n_blocks", len(blist) or 1), ("splits", {"development": len(dev), "evaluation": len(ev), "blind_pass": len(blind), "held_out": len(held)}),
        ("settings", cfg.summary()), ("warnings", warns),
        ("reminder", "The corpus must be de-identified before anything leaves the machine, and consent terms decide which "
                     "vendors may receive it. Record both in data_governance."),
    ])
    write_json(W / "manifest.json", manifest)
    print("prepare: %d units%s; development %d, evaluation %d, blind pass %d (%s), held out %d; blocks %d; workspace %s"
          % (len(uids), " with context" if manifest["has_context"] else "", len(dev), len(ev), len(blind), note, len(held), len(blist) or 1, W))
    return 0


# --------------------------------------------------------------------------- shared prompt values
def vocab(corpus=None) -> dict:
    s = cfg.study
    corpus = corpus or load_corpus()
    return {"UNIT": s["unit_name"], "UNITS": s["unit_name_plural"], "RESPONDENT": s["respondent_name"],
            "RESPONDENTS": s["respondent_name_plural"], "CORPUS_DESCRIPTION": (s.get("corpus_description") or "").strip(),
            "SCOPE_RULE": (s.get("scope_rule") or "").strip(), "MIN_SUPPORT": cfg.t["support_floor"],
            "MAX_LABEL_WORDS": cfg.t["max_label_words"], "CONTEXT": has_context(corpus),
            "EXAMPLE_UID": next(iter(corpus))}


def rq_line(q) -> str:
    return "%s (%s)" % (q["id"], q["text"])


def rq_block_one(qid: str) -> str:
    q = cfg.rqs[qid]
    out = ["- **%s** %s" % (qid, q["text"])]
    if q["rationale"]:
        out += ["", "*What the question means:* %s" % q["rationale"]]
    if len(cfg.rqs) > 1:
        others = "; ".join("%s %s" % (k, v["text"]) for k, v in cfg.rqs.items() if k != qid)
        out += ["", "This is one of %d readings you do, one per research question. In this reading, propose only codes that "
                    "answer this question, and read every %s for it. %s The other questions are covered by your other readings: %s."
                % (len(cfg.rqs), cfg.study["unit_name"], (cfg.study.get("scope_rule") or "").strip(), others)]
    elif cfg.study.get("scope_rule"):
        out += ["", cfg.study["scope_rule"].strip()]
    return "\n".join(out)


def rq_block_all() -> str:
    lines = []
    for k, q in cfg.rqs.items():
        lines.append("- **%s** %s" % (k, q["text"]) + ("  \n  *What the question means:* %s" % q["rationale"] if q["rationale"] else ""))
    return "\n".join(lines)


# --------------------------------------------------------------------------- discovery
def reading_jobs(corpus=None) -> list:
    """One reading per analyst x research question x block, with its brief written."""
    corpus = corpus or load_corpus()
    v = vocab(corpus)
    bl = blocks()
    jobs = []
    for L in cfg.analysts:
        for qid, q in cfg.rqs.items():
            for b in bl:
                tag = "%s_%s" % (L, q["slug"]) + ("_%s" % b["id"] if b["id"] else "")
                prefix = "%s-%s" % (L, q["slug"]) + ("-%s" % b["id"] if b["id"] else "")
                cfile = ("data/blocks/%s.txt" % b["id"]) if b["id"] else "data/corpus.txt"
                out = "discovery/v0/per_reading/analyst_%s.json" % tag
                vals = dict(v, ANALYST=L, RQ_BLOCK=rq_block_one(qid), CORPUS_FILE=cfile, N_UNITS=len(b["units"]),
                            ID_PREFIX=prefix, RQ_ID=qid, OUTPUT_PATH=out, EXAMPLE_UID=b["units"][0])
                if b["id"]:
                    vals["CORPUS_DESCRIPTION"] = (v["CORPUS_DESCRIPTION"] + " This file is block %s of %d of the corpus; "
                                                  "read every unit in it." % (b["id"], len(bl))).strip()
                brief = P.write("01_discovery_analyst.md", vals, D("briefs", "discovery", "analyst_%s.md" % tag))
                jobs.append(OrderedDict([("analyst", L), ("rq", qid), ("block", b["id"]), ("tag", tag), ("brief", brief),
                                         ("corpus_label", cfile), ("corpus_path", W / cfile), ("output", out),
                                         ("units", b["units"]), ("values", vals)]))
    return jobs


def cmd_discovery_briefs(args):
    jobs = reading_jobs()
    print("discovery-briefs: %d readings (%d analysts x %d questions x %d blocks); briefs in %s"
          % (len(jobs), len(cfg.analysts), len(cfg.rqs), len(blocks()), W / "briefs" / "discovery"))
    for j in jobs:
        print("   %s -> %s" % (j["brief"].relative_to(W), j["output"]))
    return 0


ELLIPSIS = re.compile(r"\s*(?:\[\.\.\.\]|\[\u2026\]|\.\.\.|\u2026)\s*")


def _norm(s: str) -> str:
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2014", "-").replace("\u2013", "-").replace("\u00a0", " ").replace("`", "").replace("*", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def _in_sequence(frags, source) -> bool:
    pos = 0
    for f in frags:
        i = source.find(f, pos)
        if i < 0:
            return False
        pos = i + len(f)
    return True


def quote_status(quote: str, source: str) -> str:
    """'exact': every fragment (split only at an ellipsis the quoter inserted) occurs verbatim and in
    order; 'normalized': it matches only after normalizing case, whitespace or punctuation (diagnostic,
    never accepted); 'absent': no match."""
    q = (quote or "").strip()
    if len(q) >= 2 and q[0] in "\"\u201c" and q[-1] in "\"\u201d":
        q = q[1:-1].strip()
    frags = [f.strip() for f in ELLIPSIS.split(q) if f.strip()]
    if not frags:
        return "absent"
    if _in_sequence(frags, source):
        return "exact"
    nf = [f.strip(" .\"'") for f in ELLIPSIS.split(_norm(q)) if f.strip(" .\"'")]
    return "normalized" if nf and _in_sequence(nf, _norm(source)) else "absent"


def validate_discovery(d: dict, corpus, L: str, expected=None, check_n_read=True):
    """Provenance check of one discovery file. `expected`: the unit ids this reading was given."""
    errs, warns = [], []
    t = cfg.t
    floor, min_q = int(t["support_floor"]), int(t["min_quotes"])
    text = {u: r["text"] for u, r in corpus.items()}
    scope = list(expected) if expected is not None else list(text)
    sset = set(scope)
    if d.get("analyst") not in (None, L):
        warns.append("analyst field is %r, expected %r" % (d.get("analyst"), L))
    if check_n_read and d.get("n_read") != len(scope):
        errs.append("n_read %r != %d units supplied" % (d.get("n_read"), len(scope)))
    codes = d.get("codes") or []
    if not all(isinstance(c, dict) for c in codes):
        return ["codes must be a list of code objects"], [], OrderedDict([("n_codes", 0), ("n_units_covered", 0), ("n_uncodeable", 0),
                ("units_neither_coded_nor_uncodeable", []), ("n_units_neither_coded_nor_uncodeable", 0)])
    ids = [c.get("id") for c in codes]
    if len(ids) != len(set(ids)):
        errs.append("duplicate code ids: %s" % sorted({i for i in ids if ids.count(i) > 1}))
    theme_ids = {x.get("theme_id") for x in d.get("candidate_themes") or []}
    for c in codes:
        cid = c.get("id", "?")
        parts = [str(p) for p in c.get("participants") or []]
        if len(parts) != len(set(parts)):
            errs.append("%s: duplicate unit ids in participants" % cid)
        parts = list(dict.fromkeys(parts))
        unknown = [p for p in parts if p not in sset]
        if unknown:
            errs.append("%s: unit ids not in this reading's input %s" % (cid, unknown[:10]))
        parts = [p for p in parts if p in sset]
        if c.get("n_participants") not in (None, len(parts)):
            warns.append("%s: n_participants %r != %d listed" % (cid, c.get("n_participants"), len(parts)))
        if len(parts) < floor:
            warns.append("%s: below the %d-unit floor (n=%d); reported honestly, applied at reconciliation" % (cid, floor, len(parts)))
        if not parts:
            errs.append("%s: no valid participants" % cid)
        if c.get("candidate_theme") and c["candidate_theme"] not in theme_ids:
            warns.append("%s: candidate_theme %r does not resolve" % (cid, c["candidate_theme"]))
        aq = c.get("anchor_quotes") or []
        need = min(min_q, len(parts))
        quoted = set()
        seen_q = set()
        for q in aq:
            uid = str(q.get("uid"))
            key = (uid, q.get("quote"))
            if key in seen_q:
                errs.append("%s: duplicate anchor quote for %s" % (cid, uid))
            seen_q.add(key)
            if uid not in text:
                errs.append("%s: quote uid %r unknown" % (cid, uid))
                continue
            if uid not in parts:
                errs.append("%s: quote uid %s not in participants" % (cid, uid))
            st = quote_status(q.get("quote", ""), text[uid])
            if st == "normalized":
                errs.append("%s: quote not verbatim for %s (matches only after normalizing case, whitespace or punctuation; "
                            "not accepted): %r" % (cid, uid, (q.get("quote") or "")[:90]))
            elif st == "absent":
                errs.append("%s: quote not verbatim for %s (not found in the unit's text): %r" % (cid, uid, (q.get("quote") or "")[:90]))
            quoted.add(uid)
        if len(quoted) < need:
            errs.append("%s: quotes from %d distinct units, need %d" % (cid, len(quoted), need))
        for k in ("label", "definition"):
            if not (c.get(k) or "").strip():
                errs.append("%s: missing %s" % (cid, k))
        if c.get("layer") not in LAYERS:
            errs.append("%s: layer %r is not one of %s" % (cid, c.get("layer"), LAYERS))
        if c.get("rq") and c["rq"] not in cfg.rqs:
            errs.append("%s: rq %r is not a research question in the config" % (cid, c["rq"]))
        if len((c.get("label") or "").split()) > int(t["max_label_words"]):
            warns.append("%s: label over %s words" % (cid, t["max_label_words"]))
    for th in d.get("candidate_themes") or []:
        for cid in th.get("codes") or []:
            if cid not in ids:
                warns.append("theme %s: code %s unknown" % (th.get("theme_id"), cid))
    unc = [str(u) for u in d.get("uncodeable") or []]
    if len(unc) != len(set(unc)):
        errs.append("duplicate unit ids in uncodeable")
    bad_unc = [u for u in unc if u not in sset]
    if bad_unc:
        errs.append("uncodeable cites unknown units %s" % bad_unc[:10])
    covered = {str(u) for c in codes for u in (c.get("participants") or [])}
    neither = [u for u in scope if u not in covered and u not in set(unc)]
    stats = OrderedDict([
        ("n_codes", len(codes)), ("n_below_floor", sum(1 for c in codes if len(set(c.get("participants") or [])) < floor)),
        ("n_quotes", sum(len(c.get("anchor_quotes") or []) for c in codes)),
        ("n_units_covered", len(covered & sset)), ("n_uncodeable", len(set(unc))),
        ("n_units_neither_coded_nor_uncodeable", len(neither)), ("units_neither_coded_nor_uncodeable", neither),
        ("n_adopted_from_adversary", sum(1 for c in codes if c.get("adopted_from_adversary"))),
        ("n_by_layer", OrderedDict((l, sum(1 for c in codes if c.get("layer") == l)) for l in LAYERS)),
    ])
    return errs, warns, stats


def merge_readings(L: str, stage: str = "v0") -> dict:
    """Merge analyst L's per-reading files into discovery/<stage>/analyst_<L>.json."""
    corpus = load_corpus()
    codes, notes = [], []
    unc_by_rq = OrderedDict()
    for j in [j for j in reading_jobs(corpus) if j["analyst"] == L]:
        d = read_json(W / j["output"])
        for c in d.get("codes", []):
            c["rq"] = j["rq"]
            if j["block"]:
                c["block"] = j["block"]
            c.pop("candidate_theme", None)
            codes.append(c)
        unc_by_rq.setdefault(j["rq"], set()).update(str(u) for u in d.get("uncodeable") or [])
        if d.get("notes"):
            notes.append("%s%s: %s" % (j["rq"], "/" + j["block"] if j["block"] else "", d["notes"]))
    nothing = set.intersection(*unc_by_rq.values()) if unc_by_rq else set()
    out = OrderedDict([("analyst", L), ("lens", "layered"), ("n_read", len(corpus)),
                       ("readings", "one per research question" + (" and block" if len(blocks()) > 1 else "")),
                       ("codes", codes), ("candidate_themes", []),
                       ("uncodeable", [u for u in corpus if u in nothing]),
                       ("uncodeable_by_rq", OrderedDict((q, [u for u in corpus if u in s]) for q, s in unc_by_rq.items())),
                       ("notes", " | ".join(notes))])
    write_json(D("discovery", stage, "analyst_%s.json" % L), out)
    return out


def cmd_merge_readings(args):
    for L in (args.analyst.split(",") if args.analyst else cfg.analysts):
        d = merge_readings(L)
        print("merge-readings %s: %d codes from %d readings" % (L, len(d["codes"]), len(cfg.rqs) * len(blocks())))
    return 0


def validate_quarantined(corpus):
    for L in cfg.analysts:
        ch = W / "discovery" / "challenges" / ("adversary_%s.json" % L)
        if not ch.exists():
            continue
        qcodes = read_json(ch).get("quarantined_codes") or []
        if not qcodes:
            continue
        errs, warns, _ = validate_discovery(OrderedDict([("analyst", L), ("codes", qcodes)]), corpus, L, check_n_read=False)
        for c in qcodes:
            if len(set(c.get("participants") or [])) < int(cfg.t["support_floor"]):
                errs.append("%s: a quarantined candidate needs at least %s supporting units" % (c.get("id"), cfg.t["support_floor"]))
        out = OrderedDict([("adversary_for", L), ("n_quarantined", len(qcodes)), ("status", "PASS" if not errs else "FAIL"),
                           ("errors", errs), ("warnings", warns),
                           ("per_code", [OrderedDict([("id", c.get("id")), ("label", c.get("label")),
                                                      ("n_units", len(set(c.get("participants") or []))),
                                                      ("errors", [e for e in errs if e.startswith(str(c.get("id")) + ":")])]) for c in qcodes])])
        write_json(D("discovery", "validation", "quarantined_%s.json" % L), out)
        print("validate quarantined/%s: %s, %d candidate codes, %d errors (reported; never blocks the analyst)" % (L, out["status"], len(qcodes), len(errs)))


def cmd_validate(args):
    corpus = load_corpus()
    stage = args.stage
    any_err = False
    if stage == "v1":
        validate_quarantined(corpus)
    for L in cfg.analysts:
        p = W / "discovery" / stage / ("analyst_%s.json" % L)
        if not p.exists():
            print("validate %s/%s: file missing" % (stage, L))
            any_err = True
            continue
        try:
            d = read_json(p)
        except json.JSONDecodeError as e:
            print("validate %s/%s: JSON error %s" % (stage, L, e))
            any_err = True
            continue
        errs, warns, stats = validate_discovery(d, corpus, L)
        if stats["n_units_neither_coded_nor_uncodeable"]:
            errs.append("%d units neither cited by a code nor listed as uncodeable" % stats["n_units_neither_coded_nor_uncodeable"])
        status = "PASS" if not errs else "FAIL"
        any_err |= bool(errs)
        prior = rj(W / "discovery" / "validation" / ("%s_repairs_%s.json" % (stage, L)))
        write_json(D("discovery", "validation", "%s_analyst_%s.json" % (stage, L)), OrderedDict([
            ("analyst", L), ("stage", stage), ("status", status), ("n_errors", len(errs)), ("n_warnings", len(warns)),
            ("errors", errs), ("warnings", warns), ("stats", stats), ("repairs", prior), ("validated_at", now())]))
        print("validate %s/%s: %s, %d codes, %d errors, %d warnings" % (stage, L, status, stats["n_codes"], len(errs), len(warns)))
        for e in errs[:30]:
            print("   ERR  %s" % e)
    return 1 if any_err else 0


def apply_delta(base: dict, delta: dict) -> dict:
    """v1 = base with the analyst's changes applied (the analyst returns only what changed)."""
    out = OrderedDict(base)
    codes = OrderedDict((c["id"], c) for c in base.get("codes", []))
    for cid in delta.get("remove") or []:
        codes.pop(cid, None)
    for c in delta.get("replace") or []:
        if isinstance(c, dict) and c.get("id"):
            prev = codes.get(c["id"], {})
            for k in ("rq", "block"):
                if prev.get(k) and not c.get(k):
                    c[k] = prev[k]
            codes[c["id"]] = c
    out["codes"] = list(codes.values())
    unc = set(base.get("uncodeable") or []) | set(delta.get("uncodeable_add") or [])
    out["uncodeable"] = sorted(unc - set(delta.get("uncodeable_remove") or []))
    return out


def cmd_apply_delta(args):
    base = W / (args.base or "discovery/v0/analyst_%s.json" % args.analyst)
    delta = W / (args.delta or "discovery/v1_delta/analyst_%s.json" % args.analyst)
    out = W / (args.out or "discovery/v1/analyst_%s.json" % args.analyst)
    write_json(out, apply_delta(read_json(base), read_json(delta)))
    print("apply-delta: %s + %s -> %s" % (base.relative_to(W), delta.relative_to(W), out.relative_to(W)))
    return 0


def cmd_freeze(args):
    """Record sha256 of the pre-adversary files and make them read-only. Re-running verifies."""
    targets = {"discovery": sorted((W / "discovery" / "v0").glob("analyst_*.json")),
               "coding": sorted(p for cond in ("L", "LJ") for p in (W / "coding" / cond).glob("coder*_batch*.jsonl"))}  # v0 coding
    logp = W / "logs" / "freeze.json"
    log = rj(logp)
    changed = []
    for what, files in targets.items():
        if args.what and args.what != what:
            continue
        for f in files:
            rel = str(f.relative_to(W))
            h = hashlib.sha256(f.read_bytes()).hexdigest()
            if rel in log and log[rel]["sha256"] != h:
                changed.append(rel)
            log.setdefault(rel, OrderedDict([("sha256", h), ("frozen_at", now()), ("bytes", f.stat().st_size)]))
            os.chmod(f, 0o444)
    write_json(D("logs", "freeze.json"), log)
    print("freeze: %d files hashed and read-only%s" % (len(log), ("; CHANGED SINCE FREEZE: %s" % changed) if changed else ""))
    return 1 if changed else 0


# --------------------------------------------------------------------------- reconciliation
def flatten(d: dict, L: str, corpus):
    out = []
    for c in d.get("codes", []):
        units = [u for u in dict.fromkeys(str(x) for x in c.get("participants") or []) if u in corpus]
        out.append(OrderedDict([
            ("key", "%s:%s" % (L, c["id"])), ("analyst", L), ("layer", c.get("layer", "")), ("rq", c.get("rq", "")),
            ("label", c.get("label", "")), ("definition", c.get("definition", "")),
            ("include", c.get("include", "")), ("exclude", c.get("exclude", "")),
            ("units", units), ("n_units", len(units)), ("anchor_quotes", c.get("anchor_quotes") or []),
            ("adopted_from_adversary", bool(c.get("adopted_from_adversary"))),
        ]))
    return out


def recon_stage(cond: str) -> str:
    return "v1" if cond == "full" else "v0"


def reconcile_prepare(cond: str) -> list:
    corpus = load_corpus()
    stage = recon_stage(cond)
    codes = []
    for L in cfg.analysts:
        v = W / "discovery" / "validation" / ("%s_analyst_%s.json" % (stage, L))
        if not v.exists() or read_json(v)["status"] != "PASS":
            raise SystemExit("analyst %s: the %s discovery file has not passed validation; run `council.py validate --stage %s`" % (L, stage, stage))
        codes += flatten(read_json(W / "discovery" / stage / ("analyst_%s.json" % L)), L, corpus)
    overlaps = []
    for i, a in enumerate(codes):
        for b in codes[i + 1:]:
            if a["analyst"] == b["analyst"] or (a["rq"] and b["rq"] and a["rq"] != b["rq"]):
                continue  # codes answering different research questions are never merged
            sa, sb = set(a["units"]), set(b["units"])
            shared = len(sa & sb)
            if not shared:
                continue
            overlaps.append(OrderedDict([
                ("a", a["key"]), ("b", b["key"]), ("label_a", a["label"]), ("label_b", b["label"]), ("rq", a["rq"]),
                ("shared", shared), ("only_a", len(sa - sb)), ("only_b", len(sb - sa)),
                ("jaccard", round(shared / len(sa | sb), 3)), ("containment", round(shared / min(len(sa), len(sb)), 3)),
                ("shared_units", sorted(sa & sb))]))
    overlaps.sort(key=lambda o: (-o["jaccard"], -o["shared"]))
    quarantined = []
    if cond == "full":
        for L in cfg.analysts:
            ch = W / "discovery" / "challenges" / ("adversary_%s.json" % L)
            if not ch.exists():
                continue
            per = {c["id"]: c for c in rj(W / "discovery" / "validation" / ("quarantined_%s.json" % L)).get("per_code", [])}
            views = {}
            for a in rj(W / "discovery" / "answers" / ("answer_%s.json" % L)).get("answers", []):
                if a.get("quarantined_view"):
                    views[a.get("challenge_id")] = OrderedDict([("view", a["quarantined_view"]), ("reason", a.get("reason", ""))])
            chd = read_json(ch)
            chs = {c.get("candidate_code_id"): c for c in chd.get("challenges", []) if c.get("candidate_code_id")}
            rq_of = {c["key"].split(":", 1)[1]: c["rq"] for c in codes if c["analyst"] == L}
            for c in chd.get("quarantined_codes") or []:
                units = [u for u in dict.fromkeys(str(x) for x in c.get("participants") or []) if u in corpus]
                chal = chs.get(c.get("id")) or {}
                rq = c.get("rq") if c.get("rq") in cfg.rqs else rq_of.get(chal.get("code_id"), "")
                quarantined.append(OrderedDict([
                    ("key", "Q:%s" % c.get("id")), ("quarantined", True), ("proposed_by", c.get("proposed_by", "adversary-%s" % L)),
                    ("critiqued_analyst", L), ("challenge_id", chal.get("id")), ("layer", c.get("layer", "")), ("rq", rq),
                    ("label", c.get("label", "")), ("definition", c.get("definition", "")), ("include", c.get("include", "")),
                    ("exclude", c.get("exclude", "")), ("units", units), ("n_units", len(units)),
                    ("anchor_quotes", c.get("anchor_quotes") or []),
                    ("validation_errors", per.get(c.get("id"), {}).get("errors", [])),
                    ("analyst_view", views.get(chal.get("id")) if chal else None)]))
    rdir = D("reconciliation", cond)
    inp = OrderedDict([("condition", cond), ("discovery_stage", stage), ("min_support", cfg.t["support_floor"]),
                       ("n_raw_codes", len(codes)),
                       ("n_by_analyst", OrderedDict((L, sum(1 for c in codes if c["analyst"] == L)) for L in cfg.analysts)),
                       ("n_quarantined", len(quarantined)), ("codes", codes), ("overlap", overlaps), ("quarantined_codes", quarantined)])
    write_json(rdir / "input.json", inp)
    R.write_csv(rdir / "overlap_table.csv", [OrderedDict((k, ("|".join(v) if isinstance(v, list) else v)) for k, v in o.items()) for o in overlaps])
    gmin, gmax = cfg.d["reconciliation"]["groups_per_rq"]
    v = vocab(corpus)
    jobs = []
    for qid, q in cfg.rqs.items():
        keys = {c["key"] for c in codes if c["rq"] == qid}
        d = D("reconciliation", cond, "per_rq", q["slug"], "x.json").parent
        slim = OrderedDict([("research_question", "%s %s" % (qid, q["text"])), ("min_support", cfg.t["support_floor"]),
                            ("codes", [OrderedDict((k, val if k != "anchor_quotes" else val[:3]) for k, val in c.items()) for c in codes if c["key"] in keys]),
                            ("overlap", [OrderedDict((k, o[k]) for k in o if k not in ("label_a", "label_b", "shared_units"))
                                         for o in overlaps if o["a"] in keys and o["b"] in keys]),
                            ("quarantined_codes", [x for x in quarantined if x["rq"] == qid])])
        slim["n_raw_codes"] = len(slim["codes"])
        write_json(d / "input.json", slim)
        vals = dict(v, RQ_LINE=rq_line(q), N_UNITS=len(corpus), N_RAW_CODES=len(slim["codes"]), N_OVERLAPS=len(slim["overlap"]),
                    N_QUARANTINED=len(slim["quarantined_codes"]), GROUPS_MIN=gmin, GROUPS_MAX=gmax)
        bdir = D("briefs", "reconciliation", cond, q["slug"], "x.md").parent
        job = OrderedDict([("rq", qid), ("slug", q["slug"]), ("dir", d), ("input", d / "input.json"), ("n_codes", len(slim["codes"])),
                           ("brief", P.write("02_reconciler.md", vals, bdir / "reconcile.md"))])
        if cond == "full":
            job["adversary_brief"] = P.write("02_reconciliation_adversary.md", vals, bdir / "reconcile_adversary.md")
            job["answer_brief"] = P.write("02_reconciler_answer.md", vals, bdir / "reconcile_answer.md")
        jobs.append(job)
    print("reconcile-prepare (%s, discovery %s): %d raw codes (%s), %d overlapping cross-analyst pairs, %d quarantined candidates; %d per-question calls"
          % (cond, stage, len(codes), ", ".join("%s=%d" % kv for kv in inp["n_by_analyst"].items()), len(overlaps), len(quarantined), len(jobs)))
    return jobs


def cmd_reconcile_prepare(args):
    for j in reconcile_prepare(args.cond):
        print("   %s: %d raw codes -> brief %s, input %s, write %s" % (j["rq"], j["n_codes"], j["brief"].relative_to(W),
              j["input"].relative_to(W), (j["dir"] / "merge_plan.json").relative_to(W)))
    return 0


def combine_plans(cond: str) -> Path:
    """Join the per-question plans; group ids are prefixed by the question so they stay unique."""
    base = W / "reconciliation" / cond
    use_revised = all((base / "per_rq" / q["slug"] / "merge_plan_revised.json").exists() for q in cfg.rqs.values()) and cond == "full"
    files = ["merge_plan.json"] + (["merge_plan_revised.json", "adversary_challenges.json", "reconciler_answers.json"] if use_revised else [])
    for fname in files:
        out = OrderedDict([("groups", []), ("relations", []), ("quarantined_assessment", []), ("challenges", []), ("answers", []), ("notes", [])])
        for qid, q in cfg.rqs.items():
            p = base / "per_rq" / q["slug"] / fname
            if not p.exists():
                if fname == "merge_plan.json" and any(c for c in read_json(base / "per_rq" / q["slug"] / "input.json")["codes"]):
                    raise SystemExit("missing %s" % p.relative_to(W))
                continue
            d = read_json(p)
            s = q["slug"]
            for g in d.get("groups", []):
                g["group_id"] = "%s-%s" % (s, g.get("group_id"))
                g["rq"] = g.get("rq") or qid
                out["groups"].append(g)
            for x in d.get("relations", []):
                x["from"], x["to"] = "%s-%s" % (s, x.get("from")), "%s-%s" % (s, x.get("to"))
                out["relations"].append(x)
            for x in d.get("quarantined_assessment", []):
                x["to"] = "%s-%s" % (s, x.get("to")) if x.get("to") else x.get("to")
                out["quarantined_assessment"].append(x)
            for x in d.get("challenges", []):
                x["id"] = "%s-%s" % (s, x.get("id"))
                out["challenges"].append(x)
            for x in d.get("answers", []):
                x["challenge_id"] = "%s-%s" % (s, x.get("challenge_id"))
                out["answers"].append(x)
            if d.get("notes"):
                out["notes"].append("%s: %s" % (qid, d["notes"]))
        out["notes"] = " | ".join(out["notes"])
        write_json(base / fname, OrderedDict((k, v) for k, v in out.items() if v))
    return base / ("merge_plan_revised.json" if use_revised else "merge_plan.json")


def reconcile_apply(cond: str, plan_path: Path | None = None):
    inp = read_json(W / "reconciliation" / cond / "input.json")
    plan_path = plan_path or combine_plans(cond)
    plan = read_json(plan_path)
    floor = int(cfg.t["support_floor"])
    raw = OrderedDict((c["key"], c) for c in inp["codes"])
    membership = defaultdict(list)
    groups, errors = [], []

    def group_record(gid, rq, label, definition, include, exclude, mem, sub, rationale):
        units = []
        for m in mem:
            units += [u for u in (sub.get(m) or raw[m]["units"]) if u in raw[m]["units"]]
        units = list(dict.fromkeys(units))
        return OrderedDict([
            ("group_id", gid), ("rq", rq), ("label", label), ("definition", definition), ("include", include), ("exclude", exclude),
            ("members", mem), ("member_units", OrderedDict((m, sub[m]) for m in mem if m in sub)),
            ("n_analysts", len({raw[m]["analyst"] for m in mem})), ("analysts", sorted({raw[m]["analyst"] for m in mem})),
            ("layers", OrderedDict((l, sum(1 for m in mem if raw[m]["layer"] == l)) for l in LAYERS if any(raw[m]["layer"] == l for m in mem))),
            ("layer_origin", "semantic-only" if all(raw[m]["layer"] == "semantic" for m in mem) else
                             "no-semantic-member" if not any(raw[m]["layer"] == "semantic" for m in mem) else "mixed"),
            ("source_codes", [OrderedDict([("key", m), ("layer", raw[m]["layer"]), ("label", raw[m]["label"]), ("n_units", raw[m]["n_units"])]) for m in mem]),
            ("units", units), ("n_units", len(units)),
            ("adopted_from_adversary", any(raw[m]["adopted_from_adversary"] for m in mem)),
            ("anchor_quotes", [q for m in mem for q in raw[m]["anchor_quotes"]][:6]), ("rationale", rationale)])

    for i, g in enumerate(plan.get("groups", []), 1):
        gid = g.get("group_id") or "G%02d" % i
        mem = [m for m in dict.fromkeys(g.get("members", [])) if m in raw]
        miss = [m for m in g.get("members", []) if m not in raw]
        if miss:
            errors.append("group %s %r: unknown members %s" % (gid, g.get("label"), miss))
        if not mem:
            continue
        rqs = {raw[m]["rq"] for m in mem}
        if len(rqs) > 1:
            errors.append("group %s mixes research questions %s" % (gid, sorted(rqs)))
        for m in mem:
            membership[m].append(gid)
        groups.append(group_record(gid, g.get("rq") or raw[mem[0]]["rq"], (g.get("label") or "").strip(), (g.get("definition") or "").strip(),
                                   (g.get("include") or "").strip(), (g.get("exclude") or "").strip(), mem, g.get("member_units") or {},
                                   g.get("rationale", "")))
    for m, gids in membership.items():
        if len(gids) > 1:
            unsub = [g["group_id"] for g in groups if g["group_id"] in gids and m not in g["member_units"]]
            if unsub:
                errors.append("raw code %s is in groups %s without member_units in %s (all its units counted in each)" % (m, gids, unsub))
    orphans = sorted(set(raw) - set(membership))
    if orphans:
        errors.append("orphan raw codes not placed in any group (kept as their own groups): %s" % orphans)
        for m in orphans:
            gid = "ORPHAN-%d" % (len(groups) + 1)
            membership[m].append(gid)
            r = raw[m]
            groups.append(group_record(gid, r["rq"], r["label"], r["definition"], r["include"], r["exclude"], [m], {}, "ORPHAN: placed mechanically"))
    kept = [g for g in groups if g["n_units"] >= floor]
    dropped = [g for g in groups if g["n_units"] < floor]
    rq_order = list(cfg.rqs)
    kept.sort(key=lambda g: (rq_order.index(g["rq"]) if g["rq"] in rq_order else 99, -g["n_analysts"], -g["n_units"], g["label"]))
    gid_to_code = {g["group_id"]: "T%02d" % i for i, g in enumerate(kept, 1)}
    codes = [OrderedDict([("id", gid_to_code[g["group_id"]]), *g.items()]) for g in kept]
    relations = []
    for r in plan.get("relations", []) or []:
        t = REL_ALIAS.get(r.get("type"), r.get("type"))
        if t not in REL_TYPES:
            errors.append("relation with unknown type %r ignored" % t)
            continue
        relations.append(OrderedDict([("type", t), ("from", r.get("from")), ("to", r.get("to")),
                                      ("from_code", gid_to_code.get(r.get("from"))), ("to_code", gid_to_code.get(r.get("to"))),
                                      ("note", r.get("note", ""))]))
    provenance = OrderedDict((m, OrderedDict([("groups", gids), ("codes", [gid_to_code[g] for g in gids if g in gid_to_code]),
                                              ("dropped_groups", [g for g in gids if g not in gid_to_code])]))
                             for m, gids in sorted(membership.items()))
    qa = {q.get("key"): q for q in plan.get("quarantined_assessment", []) or []}
    quarantined = []
    for q in inp.get("quarantined_codes", []):
        qq = OrderedDict(q)
        a = qa.get(q["key"])
        qq["reconciler_assessment"] = OrderedDict([("relation", a.get("relation")), ("to_group", a.get("to")),
                                                   ("to_code", gid_to_code.get(a.get("to"))), ("note", a.get("note", ""))]) if a else None
        qq["status"] = "QUARANTINED (author review decides)"
        quarantined.append(qq)
    book = OrderedDict([
        ("status", "CANDIDATE"), ("condition", cond), ("plan_used", str(plan_path.relative_to(W))),
        ("min_support", floor), ("n_raw_codes", len(raw)), ("n_groups", len(groups)), ("n_kept", len(codes)),
        ("n_dropped_below_floor", len(dropped)), ("n_multi_analyst", sum(1 for c in codes if c["n_analysts"] >= 2)),
        ("n_raw_codes_in_multiple_groups", sum(1 for g in membership.values() if len(g) > 1)),
        ("n_relations", len(relations)), ("n_quarantined", len(quarantined)),
        ("dropped", [OrderedDict([("group_id", d["group_id"]), ("rq", d["rq"]), ("label", d["label"]), ("n_units", d["n_units"]),
                                  ("members", d["members"]), ("units", d["units"])]) for d in dropped]),
        ("errors", errors), ("reconciler_notes", plan.get("notes", "")),
        ("relations", relations), ("provenance", provenance), ("quarantined", quarantined), ("codes", codes)])
    write_json(D("codebooks", "candidate_%s.json" % cond), book)
    print("reconcile-apply (%s, %s): %d groups -> %d codes kept (%d multi-analyst), %d dropped below %d units; %d relations; %d quarantined; %d errors"
          % (cond, plan_path.name, len(groups), len(codes), book["n_multi_analyst"], len(dropped), floor, len(relations), len(quarantined), len(errors)))
    for e in errors:
        print("   ! %s" % e)
    return book


def cmd_reconcile_apply(args):
    reconcile_apply(args.cond, (W / args.plan) if args.plan else None)
    return 0


# --------------------------------------------------------------------------- author review -> approved codebook
def cmd_approve(args):
    """Apply codebooks/review_edits.json (the agreed edit log of author review) to the candidate codebook.

    {"reviewed_by": "...", "status_note": "...", "blind_pass_codes_missing": ["..."], "edits": [
      {"op":"relabel","id":"T01","label":"...","definition":"...","include":"...","exclude":"...","rq":"RQ2","reason":"..."},
      {"op":"merge","into":"T01","from":["T03"],"label":"...","definition":"...","reason":"..."},
      {"op":"split","id":"T05","into":[{"id":"T05a","label":"...","definition":"...","include":"...","exclude":"...","units":["U1","U2","U3"]},
                                       {"id":"T05b", ...}],"reason":"..."},
      {"op":"move","units":["U012"],"from":"T02","to":"T05","reason":"..."},
      {"op":"drop","id":"T04","reason":"..."},
      {"op":"add","id":"T90","rq":"RQ1","label":"...","definition":"...","include":"...","exclude":"...","units":["U1","U2","U3"],"reason":"..."},
      {"op":"examples","id":"T01","positive":["U001"],"negative":["U009"]},
      {"op":"accept_quarantined","key":"Q:QA-01","id":"T91","reason":"..."},
      {"op":"reject_quarantined","key":"Q:QA-01","reason":"..."},
      {"op":"relation","type":"contrasts_with","from":"T02","to":"T07","reason":"..."},
      {"op":"drop_relation","from":"T02","to":"T07","type":"overlaps","reason":"..."} ]}
    """
    corpus = load_corpus()
    dev = set(splits().get("development") or [])
    floor = int(cfg.t["support_floor"])
    cand = W / "codebooks" / (args.candidate or "candidate_%s.json" % cfg.mode)
    book = read_json(cand)
    epath = W / "codebooks" / (args.edits or "review_edits.json")
    if not epath.exists():
        raise SystemExit("no %s: author review produces it (see AGENTS.md, Stage 3)" % epath.relative_to(W))
    edits = read_json(epath)
    by_id = OrderedDict((c["id"], c) for c in book["codes"])
    log, by_type = [], defaultdict(int)

    def new_code(cid, e, units, members, rationale, extra=()):
        return OrderedDict([("id", cid), ("rq", e.get("rq", "")), ("label", e.get("label", "")), ("definition", e.get("definition", "")),
                            ("include", e.get("include", "")), ("exclude", e.get("exclude", "")), ("members", members),
                            ("n_analysts", 0), ("analysts", []), ("source_codes", []), ("units", units), ("n_units", len(units)),
                            ("adopted_from_adversary", False), ("anchor_quotes", []), ("rationale", rationale), *extra])

    for e in edits.get("edits", []):
        op, reason = e.get("op"), e.get("reason", "")
        if op == "relabel" and e.get("id") in by_id:
            c = by_id[e["id"]]
            before = c["label"]
            for k in ("label", "definition", "include", "exclude", "rq"):
                if e.get(k):
                    c[k] = e[k]
            log.append(OrderedDict([("op", op), ("id", e["id"]), ("before", before), ("after", c["label"]), ("rq", c.get("rq")), ("reason", reason)]))
        elif op == "merge" and e.get("into") in by_id:
            tgt, merged = by_id[e["into"]], []
            for f in e.get("from", []):
                if f in by_id and f != e["into"]:
                    src = by_id.pop(f)
                    tgt["members"] = tgt["members"] + src["members"]
                    tgt["source_codes"] = tgt.get("source_codes", []) + src.get("source_codes", [])
                    tgt["units"] = list(dict.fromkeys(tgt["units"] + src["units"]))
                    tgt["n_units"] = len(tgt["units"])
                    tgt["analysts"] = sorted({m.split(":")[0] for m in tgt["members"] if ":" in m and not m.startswith("Q:")})
                    tgt["n_analysts"] = len(tgt["analysts"])
                    tgt["anchor_quotes"] = (tgt.get("anchor_quotes", []) + src.get("anchor_quotes", []))[:6]
                    tgt.setdefault("merged_at_review", []).append(OrderedDict([("id", f), ("label", src["label"])]))
                    merged.append(f)
            for k in ("label", "definition", "include", "exclude"):
                if e.get(k):
                    tgt[k] = e[k]
            log.append(OrderedDict([("op", op), ("into", e["into"]), ("from", merged), ("reason", reason)]))
        elif op == "split" and e.get("id") in by_id:
            src = by_id[e["id"]]
            parts, ok = [], True
            for part in e.get("into", []):
                units = [u for u in dict.fromkeys(part.get("units", [])) if u in corpus]
                if not part.get("id") or (part["id"] in by_id and part["id"] != e["id"]) or len(units) < floor:
                    ok = False
                parts.append((part, units))
            if ok and len(parts) >= 2:
                by_id.pop(e["id"])
                for part, units in parts:
                    p = dict(part, rq=part.get("rq") or src.get("rq", ""))
                    by_id[part["id"]] = new_code(part["id"], p, units, src["members"], "split at review from %s: %s" % (e["id"], reason),
                                                 extra=[("split_from", e["id"])])
                log.append(OrderedDict([("op", op), ("id", e["id"]), ("into", [p["id"] for p, _ in parts]), ("reason", reason)]))
            else:
                log.append(OrderedDict([("op", "IGNORED split"), ("id", e["id"]), ("reason", "each part needs a new id and at least %d cited units" % floor)]))
                continue
        elif op == "move" and e.get("from") in by_id and e.get("to") in by_id:
            src, dst = by_id[e["from"]], by_id[e["to"]]
            moved = [u for u in e.get("units", []) if u in src["units"]]
            src["units"] = [u for u in src["units"] if u not in moved]
            src["n_units"] = len(src["units"])
            dst["units"] = list(dict.fromkeys(dst["units"] + moved))
            dst["n_units"] = len(dst["units"])
            log.append(OrderedDict([("op", op), ("from", e["from"]), ("to", e["to"]), ("units", moved), ("reason", reason)]))
        elif op == "drop" and e.get("id") in by_id:
            c = by_id.pop(e["id"])
            book.setdefault("dropped_at_review", []).append(OrderedDict([("id", e["id"]), ("label", c["label"]), ("n_units", c["n_units"]), ("reason", reason)]))
            log.append(OrderedDict([("op", op), ("id", e["id"]), ("label", c["label"]), ("reason", reason)]))
        elif op == "add":
            units = [u for u in dict.fromkeys(e.get("units", [])) if u in corpus]
            if len(units) >= floor and e.get("id") and e["id"] not in by_id:
                by_id[e["id"]] = new_code(e["id"], e, units, ["REVIEW"], "added at review: %s" % reason)
                log.append(OrderedDict([("op", op), ("id", e["id"]), ("n_units", len(units)), ("reason", reason)]))
            else:
                log.append(OrderedDict([("op", "IGNORED add"), ("id", e.get("id")), ("reason", "needs at least %d cited units and a new id" % floor)]))
                continue
        elif op == "examples" and e.get("id") in by_id:
            pos = [u for u in e.get("positive", []) if u in corpus]
            neg = [u for u in e.get("negative", []) if u in corpus]
            outside = [u for u in pos + neg if dev and u not in dev]
            if outside:
                print("   ! examples for %s outside the development units ignored: %s" % (e["id"], outside))
            by_id[e["id"]]["examples"] = OrderedDict([("positive", [u for u in pos if not dev or u in dev]),
                                                      ("negative", [u for u in neg if not dev or u in dev])])
            log.append(OrderedDict([("op", op), ("id", e["id"]), ("ignored_not_development", outside)]))
        elif op == "accept_quarantined":
            q = next((q for q in book.get("quarantined", []) if q["key"] == e.get("key")), None)
            if q and q["n_units"] >= floor and e.get("id") and e["id"] not in by_id:
                q["status"] = "ACCEPTED at review as %s" % e["id"]
                qe = dict(q, **{k: e[k] for k in ("label", "definition", "include", "exclude", "rq") if e.get(k)})
                by_id[e["id"]] = new_code(e["id"], qe, list(q["units"]), [q["key"]], "quarantined candidate accepted at review: %s" % reason,
                                          extra=[("adopted_from_adversary", True), ("quarantined_origin", q["proposed_by"])])
                by_id[e["id"]]["anchor_quotes"] = q["anchor_quotes"][:6]
                log.append(OrderedDict([("op", op), ("key", e["key"]), ("id", e["id"]), ("n_units", q["n_units"]), ("reason", reason)]))
            else:
                log.append(OrderedDict([("op", "IGNORED accept_quarantined"), ("key", e.get("key")), ("reason", "unknown key, below floor, or id in use")]))
                continue
        elif op == "reject_quarantined":
            q = next((q for q in book.get("quarantined", []) if q["key"] == e.get("key")), None)
            if not q:
                log.append(OrderedDict([("op", "IGNORED reject_quarantined"), ("key", e.get("key"))]))
                continue
            q["status"], q["review_reason"] = "REJECTED at review", reason
            log.append(OrderedDict([("op", op), ("key", e["key"]), ("reason", reason)]))
        elif op == "relation":
            book.setdefault("relations", []).append(OrderedDict([("type", REL_ALIAS.get(e.get("type"), e.get("type"))), ("from_code", e.get("from")),
                                                                 ("to_code", e.get("to")), ("note", reason), ("added_at_review", True)]))
            log.append(OrderedDict([("op", op), ("type", e.get("type")), ("from", e.get("from")), ("to", e.get("to")), ("reason", reason)]))
        elif op == "drop_relation":
            hit = [r for r in book.get("relations", []) if r.get("from_code") == e.get("from") and r.get("to_code") == e.get("to")
                   and (not e.get("type") or r.get("type") == e.get("type"))]
            for r in hit:
                r["dropped_at_review"], r["active"], r["review_reason"] = True, False, reason
            log.append(OrderedDict([("op", op), ("from", e.get("from")), ("to", e.get("to")), ("n_dropped", len(hit)), ("reason", reason)]))
        else:
            log.append(OrderedDict([("op", "IGNORED"), ("edit", json.dumps(e)[:120])]))
            continue
        by_type[op] += 1
    final = [c for c in by_id.values() if c["n_units"] >= floor]
    for c in by_id.values():
        if c["n_units"] < floor:
            book.setdefault("dropped_at_review", []).append(OrderedDict([("id", c["id"]), ("label", c["label"]), ("n_units", c["n_units"]),
                                                                         ("reason", "below the support floor after review edits")]))
    live = {c["id"] for c in final}
    for r in book.get("relations", []):
        r["active"] = bool(r.get("from_code") in live and r.get("to_code") in live) and not r.get("dropped_at_review")
    for q in book.get("quarantined", []):
        if q["status"].startswith("QUARANTINED"):
            q["status"] = "NOT ACCEPTED at review (no decision recorded)"
    no_ex = [c["id"] for c in final if not (c.get("examples") or {}).get("positive")]
    book.update([
        ("n_quarantined_proposed", len(book.get("quarantined", []))),
        ("n_quarantined_accepted", sum(1 for q in book.get("quarantined", []) if q["status"].startswith("ACCEPTED"))),
        ("codes", final), ("status", "APPROVED"), ("version", args.version), ("n_approved", len(final)),
        ("review", OrderedDict([("reviewed_by", edits.get("reviewed_by", "")), ("status_note", edits.get("status_note", "")),
                                ("blind_pass_codes_missing", edits.get("blind_pass_codes_missing", [])),
                                ("decisions_on_reconciliation_challenges", edits.get("decisions_on_reconciliation_challenges", [])),
                                ("n_edits", len([l for l in log if not str(l["op"]).startswith("IGNORED")])),
                                ("edits_by_type", OrderedDict(sorted(by_type.items()))), ("log", log),
                                ("codes_without_positive_examples", no_ex), ("closed_at", now())])),
    ])
    out = W / "codebooks" / "approved_codebook.json"
    if out.exists() and read_json(out).get("status") == "APPROVED" and not args.force:
        raise SystemExit("an approved codebook already exists; coding must not mix codebook versions. Pass --force to replace it "
                         "before any coding has run, or start a new workspace.")
    write_json(out, book)
    write_json(D("codebooks", "approved_codebook_v%s.json" % args.version), book)
    print("approve: %d codes approved, version %s (%d dropped at review); %d edits: %s" % (
        len(final), args.version, len(book.get("dropped_at_review", [])), book["review"]["n_edits"], dict(by_type)))
    if len(edits.get("reviewed_by", "").split(",")) < 2 and " and " not in edits.get("reviewed_by", ""):
        print("   ! reviewed_by names fewer than two researchers; the method requires at least two")
    if no_ex:
        print("   ! %d codes have no positive example from the development units" % len(no_ex))
    return 0


# --------------------------------------------------------------------------- coding
def approved_book() -> dict:
    p = W / "codebooks" / "approved_codebook.json"
    if not p.exists() or read_json(p).get("status") != "APPROVED":
        raise SystemExit("the codebook is not approved; Stage 3 (author review) ends with `council.py approve`")
    return read_json(p)


def codebook_md(book) -> str:
    out = []
    for c in book["codes"]:
        out.append("- **%s**  %s%s" % (c["id"], c["label"], ("  (%s)" % c["rq"]) if c.get("rq") else ""))
        out.append("  - Definition: %s" % c["definition"])
        if c.get("include"):
            out.append("  - Include: %s" % c["include"])
        if c.get("exclude"):
            out.append("  - Exclude: %s" % c["exclude"])
        ex = c.get("examples") or {}
        if ex.get("positive"):
            out.append("  - Positive examples: %s" % ", ".join(ex["positive"]))
        if ex.get("negative"):
            out.append("  - Negative examples (do NOT code): %s" % ", ".join(ex["negative"]))
    ids = {c["id"] for c in book["codes"]}
    rels = [r for r in book.get("relations", []) if r.get("active", True) and r.get("from_code") in ids and r.get("to_code") in ids]
    if rels:
        out += ["", "Relations between codes (from reconciliation and review; a unit may carry both sides of `overlaps`, "
                    "rarely both sides of `contrasts_with`; the narrower code is preferred when both fit):"]
        out += ["- %s %s %s%s" % (r["from_code"], r["type"], r["to_code"], (": " + r["note"]) if r.get("note") else "") for r in rels]
    return "\n".join(out)


def issue_block() -> str:
    return "\n".join("- `%s`: %s" % (k, v) for k, v in cfg.issue_codes.items())


def coding_values(book, corpus, n_batches, sub=None) -> dict:
    b = sub or book
    return dict(vocab(corpus), N_BATCHES=n_batches, BATCH_SIZE=cfg.d["batch_size"], N_UNITS=len(corpus),
                RQ_BLOCK_ALL=rq_block_all(), ISSUE_BLOCK=issue_block(), ISSUE_IDS=", ".join(cfg.issue_codes),
                VALID_CODES=", ".join(c["id"] for c in b["codes"]), CODEBOOK_VERSION=book.get("version", "1.0"),
                CODEBOOK=codebook_md(b), EXAMPLE_CODE=(b["codes"][0]["id"] if b["codes"] else "T01"),
                LEAD_ASSIGNED_BELOW=cfg.t["coding_lead_assigned_below"],
                LEAD_UNASSIGNED_AT_OR_ABOVE=cfg.t["coding_lead_unassigned_at_or_above"])


def batch_ids() -> list:
    return sorted(int(p.stem.replace("batch", "")) for p in (W / "coding" / "batches").glob("batch*.txt"))


def batch_units(n: int) -> list:
    return rj(W / "coding" / "batches" / "batches.json")["batches"][str(n)]


def cmd_code_prepare(args):
    book = approved_book()
    corpus = load_corpus()
    rows = list(corpus.items())
    bs = int(args.batch_size or cfg.d["batch_size"])
    batches = [rows[i:i + bs] for i in range(0, len(rows), bs)]
    for n, batch in enumerate(batches, 1):
        lines = ["# Coding batch %d of %d: %d units" % (n, len(batches), len(batch)), ""]
        for uid, r in batch:
            lines += [unit_text_block(uid, r), ""]
        D("coding", "batches", "batch%d.txt" % n).write_text("\n".join(lines), encoding="utf-8")
    write_json(D("coding", "batches", "batches.json"), {"batch_size": bs, "batches": {str(n): [u for u, _ in b] for n, b in enumerate(batches, 1)}})
    for k in cfg.coders:
        vals = dict(coding_values(book, corpus, len(batches)), CODER=k, SCREENING=False,
                    OUTPUT_PATH="coding/v0/coder%s_batch<N>.jsonl" % k, LEADS=False)
        P.write("04_coder.md", vals, D("briefs", "coding", "coder_%s.md" % k))
        if cfg.full:
            P.write("04_coding_adversary.md", dict(vals, LEADS=cfg.decision_model_on), D("briefs", "coding", "coding_adversary_%s.md" % k))
            P.write("04_coder_answer.md", vals, D("briefs", "coding", "coding_answer_%s.md" % k))
    write_json(D("coding", "manifest.json"), OrderedDict([
        ("n_batches", len(batches)), ("batch_size", bs), ("n_units", len(rows)), ("codebook_version", book.get("version")),
        ("codes", [c["id"] for c in book["codes"]]), ("issue_codes", list(cfg.issue_codes)), ("uncovered", UNCOVERED)]))
    print("code-prepare: %d units in %d batches of up to %d; %d codes; briefs for coders %s%s" % (
        len(rows), len(batches), bs, len(book["codes"]), ", ".join(cfg.coders), " (with adversary and answer briefs)" if cfg.full else ""))
    return 0


# --------------------------------------------------------------------------- consensus
FALLBACK = {"LJA": "LJ", "LA": "L"}
CONDITIONS = ["L", "LJ", "LJA", "LA"]


def adversary_base() -> str:
    """Full: the coding adversaries critique the screened coding (LJ) when the decision model is on,
    otherwise the unscreened coding (L); their output is LJA or LA."""
    return "LJ" if cfg.decision_model_on else "L"


def adversary_cond() -> str:
    return "LJA" if cfg.decision_model_on else "LA"


def uncertain_pairs(cond: str):
    """Full: consensus pairs the decision model scored below the coding-lead threshold go to the spot-check."""
    scr = W / "coding" / "jev" / "screen.json"
    if not (cfg.full and scr.exists() and cond in ("LJ", "LJA")):
        return set()
    sc = read_json(scr)["scores"]
    lo = float(cfg.t["coding_lead_assigned_below"])
    cons = W / "results" / cond / "consensus.csv"
    if not cons.exists():
        return None
    return {(r["uid"], r["code"]) for r in read_csv(cons)
            if sc.get(r["uid"], {}).get(r["code"]) is not None and sc[r["uid"]][r["code"]] < lo}


def spot_decisions():
    p = W / "human" / "05_spot_check" / "decisions.csv"
    if not p.exists():
        return {}
    out = {}
    for r in read_csv(p):
        v = (r.get("keep") or r.get("decision") or "").strip().lower()
        if v in ("y", "yes", "keep", "1", "true"):
            out[(r["uid"], r["code"])] = True
        elif v in ("n", "no", "remove", "0", "false"):
            out[(r["uid"], r["code"])] = False
    return out


def consensus(cond: str):
    corpus = load_corpus()
    book = approved_book()
    folder = W / "coding" / cond
    rows, coders, problems = R.load_coded(folder, corpus)
    if not rows:
        print("consensus %s: no coded files in %s" % (cond, folder.relative_to(W)))
        return None
    if cond in FALLBACK:
        have = {(r["coder"], r["batch"]) for r in rows}
        fb, _, _ = R.load_coded(W / "coding" / FALLBACK[cond], corpus)
        added = set()
        for r in fb:
            if (r["coder"], r["batch"]) not in have:
                rows.append(r)
                added.add((r["coder"], r["batch"]))
        if added:
            problems.append("%s missing for %s; their %s coding is used" % (cond, sorted(added), FALLBACK[cond]))
        coders = sorted({r["coder"] for r in rows})
    sp = splits()
    rel_units = list(corpus) if cfg.d["reliability"]["units"] == "all" else (sp.get("evaluation") or list(corpus))
    dec = low_alpha_decisions() if cond == primary_condition() else {}
    res = R.run(rows=rows, coders=coders, problems=problems, corpus=corpus, book=book, cfg=cfg, rel_units=rel_units,
                out=D("results", cond), label=cond, low_alpha_decisions=dec)
    unc = uncertain_pairs(cond)
    if unc:
        res = R.run(rows=[OrderedDict(r) for r in res["rows"]], coders=coders, problems=problems, corpus=corpus, book=book, cfg=cfg,
                    rel_units=rel_units, out=W / "results" / cond, label=cond, uncertain_pairs=unc, spot_decisions=spot_decisions(),
                    low_alpha_decisions=dec)
    return res


def cmd_consensus(args):
    conds = [args.cond] if args.cond else [c for c in CONDITIONS if any((W / "coding" / c).glob("*.jsonl"))]
    res = OrderedDict()
    for c in conds:
        r = consensus(c)
        if r:
            res[c] = r
    b0, b1 = (adversary_base(), adversary_cond()) if cfg.full else (None, None)
    if b0 in res and b1 in res:
        cells = {s: {(r["coder"], r["uid"], c) for r in res[s]["rows"] for c in r["codes"]} for s in (b0, b1)}
        added, removed = cells[b1] - cells[b0], cells[b0] - cells[b1]
        c0 = {(r["uid"], r["code"]) for r in res[b0]["cons"]}
        c1 = {(r["uid"], r["code"]) for r in res[b1]["cons"]}
        per = OrderedDict((k, OrderedDict([("n_added", sum(1 for x in added if x[0] == k)), ("n_removed", sum(1 for x in removed if x[0] == k))]))
                          for k in sorted({x[0] for x in added | removed}))
        diff = OrderedDict([("v0", b0), ("v1", b1), ("n_coder_cells_v0", len(cells[b0])), ("n_coder_cells_v1", len(cells[b1])),
                            ("n_cells_added", len(added)), ("n_cells_removed", len(removed)),
                            ("n_consensus_pairs_v0", len(c0)), ("n_consensus_pairs_v1", len(c1)),
                            ("consensus_pairs_gained", sorted("%s:%s" % p for p in c1 - c0)),
                            ("consensus_pairs_lost", sorted("%s:%s" % p for p in c0 - c1)), ("per_coder", per)])
        write_json(D("results", "v0_v1_diff.json"), diff)
        print("v0 (%s) -> v1 (%s): %d coder cells added, %d removed; consensus pairs %d -> %d" % (b0, b1, len(added), len(removed), len(c0), len(c1)))
    if res:
        cmd_dashboard(args)
    return 0


def cmd_dashboard(args):
    import dashboard as DB
    DB.bind(sys.modules[__name__])
    print("dashboard: %s" % DB.write())
    return 0


# --------------------------------------------------------------------------- status
def primary_condition() -> str:
    return adversary_cond() if cfg.full else "L"


def low_alpha_decisions() -> dict:
    """The researchers' decisions on codes below the alpha floor: human/06_low_alpha/decisions.csv."""
    p = W / "human" / "06_low_alpha" / "decisions.csv"
    if not p.exists():
        return {}
    out = OrderedDict()
    for r in read_csv(p):
        cid, dec = (r.get("code") or "").strip(), (r.get("decision") or "").strip().lower()
        if cid and dec in ("drop", "refine"):
            out[cid] = OrderedDict([("decision", dec), ("reason", (r.get("reason") or "").strip()),
                                    ("decided_by", (r.get("decided_by") or "").strip())] +
                                   [(k, (r.get(k) or "").strip()) for k in ("new_label", "new_definition", "new_include", "new_exclude")])
        elif cid:
            print("   ! low-alpha decision for %s is %r; use drop or refine" % (cid, r.get("decision")))
    return out


def status_steps() -> list:
    """Every step of the run, in order, with whether it is done. Used by `status` and by the app."""
    def ex(*p):
        return (W.joinpath(*p)).exists()

    def step(sid, name, done, kind, run=None, note="", files=(), upload=None, show=True):
        return OrderedDict([("id", sid), ("name", name), ("done", bool(done)), ("kind", kind), ("run", run), ("note", note),
                            ("files", [f for f in files if (W / f).exists()]), ("upload", upload), ("show", show)])
    S = []
    S.append(step("prepare", "Prepare the corpus (ids, splits, samples)", ex("data", "corpus.csv"), "program", ["council.py", "prepare"]))
    S.append(step("blind-pass", "STOP 1: blind pass packet", ex("human", "01_blind_pass"), "human", ["human.py", "blind-pass"],
                  "At least two researchers open-code this sample BEFORE seeing any model output. The model stages may run meanwhile.",
                  ["human/01_blind_pass/README.md", "human/01_blind_pass/blind_pass_TEMPLATE.xlsx", "human/01_blind_pass/blind_pass_TEMPLATE_csv/Code_here.csv"],
                  {"dest": "human/01_blind_pass/returned/", "label": "Returned blind-pass sheets (kept for the record)"}))
    v0ok = all(ex("discovery", "validation", "v0_analyst_%s.json" % L) and read_json(W / "discovery" / "validation" / ("v0_analyst_%s.json" % L))["status"] == "PASS"
               for L in cfg.analysts)
    S.append(step("discovery", "Stage 1: discovery (three analysts)", v0ok, "model", ["run.py", "discovery"]))
    if cfg.full:
        S.append(step("discovery-adversary", "Stage 1, Full: decision-model leads, adversaries, answers (v1)",
                      all(ex("discovery", "validation", "v1_analyst_%s.json" % L) for L in cfg.analysts), "model", ["run.py", "discovery-adversary"]))
    need = ["lite", "full"] if cfg.full and cfg.d["reconciliation"]["run_lite_baseline_in_full"] else [cfg.mode]
    S.append(step("reconcile", "Stage 2: reconciliation" + (" (Lite baseline and Full)" if len(need) > 1 else ""),
                  all(ex("codebooks", "candidate_%s.json" % c) for c in need), "model", ["run.py", "reconcile"]))
    S.append(step("review-dashboard", "STOP 2: author review dashboard", ex("human", "02_author_review", "codebook_review.html"), "human",
                  ["human.py", "review-dashboard"],
                  "Only after the blind pass is back. Each researcher reviews every code in the dashboard and downloads their decisions.",
                  ["human/02_author_review/codebook_review.html", "human/02_author_review/README.md"],
                  {"dest": "human/02_author_review/returned/", "label": "Each reviewer's downloaded review_<name>.json"}))
    S.append(step("review-to-edits", "Compare the reviewers' decisions", ex("codebooks", "review_edits.draft.json"), "human",
                  ["human.py", "review-to-edits"], "Needs at least two review files in human/02_author_review/returned/.",
                  ["human/02_author_review/review_comparison.md", "codebooks/review_edits.draft.json"],
                  {"dest": "codebooks/review_edits.json", "label": "The agreed edit log (review_edits.json)"}))
    S.append(step("approve", "Approve the codebook (closed, versioned)", ex("codebooks", "approved_codebook.json"), "program", ["council.py", "approve"],
                  "Needs codebooks/review_edits.json, negotiated by the researchers.", ["codebooks/approved_codebook.json"]))
    S.append(step("heldout-packet", "STOP 3: held-out coding packet", ex("human", "03_heldout_coding"), "human", ["human.py", "heldout-packet"],
                  "At least two researchers code these units without seeing any model assignment, resolve differences and return one resolved.csv.",
                  ["human/03_heldout_coding/README.md", "human/03_heldout_coding/heldout_coding_TEMPLATE.xlsx",
                   "human/03_heldout_coding/heldout_coding_TEMPLATE_csv/Code_here.csv"],
                  {"dest": "human/03_heldout_coding/resolved.csv", "label": "The researchers' resolved held-out labels (resolved.csv)"}))
    S.append(step("code", "Stage 4: coding" + (", screening and coding adversaries" if cfg.full else "") + ", then consensus",
                  ex("results", primary_condition(), "summary.json"), "model", ["run.py", "code"]))
    S.append(step("spot-check", "STOP 4: spot-check packet", ex("human", "05_spot_check", "spot_check.csv"), "human", ["human.py", "spot-check"],
                  "Researchers check each row's rationale against the codebook, fill keep and note, and return decisions.csv.",
                  ["human/05_spot_check/spot_check.csv", "human/05_spot_check/README.md"],
                  {"dest": "human/05_spot_check/decisions.csv", "label": "The agreed spot-check decisions (decisions.csv)"}))
    summ = rj(W / "results" / primary_condition() / "summary.json")
    low = summ.get("codes_dropped_alpha_below_floor") or []
    dec = low_alpha_decisions()
    refine_pending = [c for c in low if dec.get(c, {}).get("decision") == "refine"]
    S.append(step("low-alpha", "STOP 5: codes below alpha %s (refine and recode, or drop)" % cfg.t["alpha_drop"],
                  bool(summ) and all(c in dec for c in low) and ex("human", "06_low_alpha"), "human", ["human.py", "low-alpha"],
                  ("%d code(s) below the floor: %s. The researchers decide, per code." % (len(low), ", ".join(low))) if low else "No code below the floor.",
                  ["human/06_low_alpha/README.md", "human/06_low_alpha/low_alpha_codes.md", "human/06_low_alpha/decisions_TEMPLATE.csv"],
                  {"dest": "human/06_low_alpha/decisions.csv", "label": "The researchers' decisions (decisions.csv)"}))
    if refine_pending:
        S.append(step("refine", "Refine: new codebook version, then recode", False, "program", ["council.py", "refine"],
                      "Codes to refine: %s. Then run Stage 4 again." % ", ".join(refine_pending)))
    S.append(step("heldout-score", "Human-council agreement (held-out sample)", ex("results", "human_council_agreement.json"), "program",
                  ["council.py", "heldout-score"], "Needs human/03_heldout_coding/resolved.csv."))
    S.append(step("report", "Report: RESULTS.md and the results dashboard", ex("RESULTS.md") and ex("dashboard.html"), "program",
                  ["council.py", "report"], files=["RESULTS.md", "dashboard.html"]))
    return S


def manual_waiting() -> list:
    d = W / "manual"
    if not d.exists():
        return []
    return [p for p in sorted(d.glob("*.prompt.md")) if not p.with_name(p.name.replace(".prompt.md", ".reply.json")).exists()]


def cmd_status(args):
    """Print what exists in the workspace and the next step, for a person or an agent."""
    errs, warns = cfg.check()
    steps = status_steps()
    conf = str(cfg.path) if cfg.path else "config.yaml"
    cmd = lambda s: "python3 pipeline/%s --config %s %s" % (s["run"][0], conf, " ".join(s["run"][1:]))
    nxt = next((s for s in steps if not s["done"]), None)
    waiting = manual_waiting()
    if getattr(args, "json", False):
        print(json.dumps(OrderedDict([("workspace", str(W)), ("mode", cfg.mode), ("config", conf), ("errors", errs), ("warnings", warns),
                                      ("steps", steps), ("manual_waiting", [str(p.relative_to(W)) for p in waiting]),
                                      ("next", nxt["id"] if nxt else None)]), indent=1))
        return 0
    print("workspace %s (mode %s)" % (W, cfg.mode))
    for e in errs:
        print("  ERROR: %s" % e)
    for w in warns:
        print("  warning: %s" % w)
    for s in steps:
        print("  [%s] %s" % ("x" if s["done"] else " ", s["name"]))
    if waiting:
        print("  %d manual prompts waiting for replies in %s" % (len(waiting), W / "manual"))
    if nxt:
        print("next: %s%s" % (cmd(nxt), ("\n      " + nxt["note"]) if nxt["note"] else ""))
    else:
        print("next: done")
    return 0


# --------------------------------------------------------------------------- record a manual run for replay
def cmd_export_replies(args):
    """Copy every answered manual prompt's reply (<workspace>/manual/*.reply.json) to a folder that the
    `replay` backend reads, with index.json recording which prompt (sha256) each reply answered."""
    import shutil
    src = W / "manual"
    dst = Path(args.to) if Path(args.to).is_absolute() else cfg.resolve(args.to)
    replies = sorted(src.glob("*.reply.json")) if src.exists() else []
    if not replies:
        raise SystemExit("no replies in %s" % src)
    dst.mkdir(parents=True, exist_ok=True)
    shas = {}
    log = W / "logs" / "calls.jsonl"
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("status") == "ok" and r.get("call_id"):
                    shas[r["call_id"]] = OrderedDict([("stage", r.get("stage")), ("role", r.get("role")), ("prompt_sha256", r.get("prompt_sha256"))])
    calls = OrderedDict()
    for f in replies:
        cid = f.name[: -len(".reply.json")]
        shutil.copyfile(f, dst / f.name)
        calls[cid] = shas.get(cid) or OrderedDict([("prompt_sha256", None)])
    write_json(dst / "index.json", OrderedDict([("recorded_from", str(W)), ("recorded_at", now()), ("n_replies", len(calls)),
                                                ("note", "Replies to manual prompts, replayed by the `replay` backend (models.<family>.replay_dir, "
                                                         "decision_model.replay_dir). No model is contacted when replaying."),
                                                ("calls", calls)]))
    print("export-replies: %d replies -> %s" % (len(calls), dst))
    return 0


# --------------------------------------------------------------------------- refine after the low-alpha decision
def cmd_refine(args):
    """Apply the researchers' `refine` decisions: archive this coding round, write a new codebook version
    (refined definitions; codes decided `drop` removed), so that `run.py code` recodes the whole corpus."""
    import shutil
    book = approved_book()
    dec = low_alpha_decisions()
    ref = OrderedDict((c, d) for c, d in dec.items() if d["decision"] == "refine")
    drop = [c for c, d in dec.items() if d["decision"] == "drop"]
    if not ref:
        raise SystemExit("no `refine` decisions in human/06_low_alpha/decisions.csv; nothing to recode")
    ids = {c["id"] for c in book["codes"]}
    for c, d in ref.items():
        if c not in ids:
            raise SystemExit("refine: %s is not a code of the approved codebook" % c)
        if not (d["new_definition"] or d["new_label"] or d["new_include"] or d["new_exclude"]):
            raise SystemExit("refine: %s has no new_definition (or new label, include, exclude) in decisions.csv" % c)
    old = str(book.get("version", "1.0"))
    try:
        major, minor = old.split(".", 1)
        new = args.version or "%s.%d" % (major, int(minor) + 1)
    except ValueError:
        new = args.version or old + ".1"
    arch = W / "archive" / ("codebook_v%s" % old)
    if arch.exists():
        raise SystemExit("%s already exists; this round was archived before" % arch.relative_to(W))
    arch.mkdir(parents=True)
    moved = []
    for rel in ("coding", "results", "human/05_spot_check", "human/06_low_alpha", "RESULTS.md", "dashboard.html"):
        src = W / rel
        if src.exists():
            dst = arch / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            for f in (src.rglob("*") if src.is_dir() else [src]):
                if f.is_file():
                    os.chmod(f, 0o644)
            shutil.move(str(src), str(dst))
            moved.append(rel)
    man = W / "manual"
    if man.exists():
        for f in list(man.glob("coding*")) + list(man.glob("jev-screen*")):
            (arch / "manual").mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(arch / "manual" / f.name))
    fz = rj(W / "logs" / "freeze.json")
    keep = OrderedDict((k, v) for k, v in fz.items() if not k.startswith("coding/"))
    write_json(arch / "freeze_coding.json", OrderedDict((k, v) for k, v in fz.items() if k.startswith("coding/")))
    write_json(W / "logs" / "freeze.json", keep)
    log = []
    codes = []
    for c in book["codes"]:
        if c["id"] in drop:
            book.setdefault("dropped_low_alpha", []).append(OrderedDict([("id", c["id"]), ("label", c["label"]), ("version", old),
                                                                        ("reason", dec[c["id"]]["reason"]), ("decided_by", dec[c["id"]]["decided_by"])]))
            log.append(OrderedDict([("op", "drop"), ("id", c["id"]), ("reason", dec[c["id"]]["reason"])]))
            continue
        if c["id"] in ref:
            d = ref[c["id"]]
            before = OrderedDict((k, c.get(k, "")) for k in ("label", "definition", "include", "exclude"))
            for k in ("label", "definition", "include", "exclude"):
                if d["new_" + k]:
                    c[k] = d["new_" + k]
            log.append(OrderedDict([("op", "refine"), ("id", c["id"]), ("before", before), ("reason", d["reason"]), ("decided_by", d["decided_by"])]))
        codes.append(c)
    book["codes"] = codes
    book["n_approved"] = len(codes)
    book["version"] = new
    book.setdefault("low_alpha_rounds", []).append(OrderedDict([("from_version", old), ("to_version", new), ("archived_to", str(arch.relative_to(W))),
                                                                ("log", log), ("at", now())]))
    write_json(W / "codebooks" / "approved_codebook.json", book)
    write_json(W / "codebooks" / ("approved_codebook_v%s.json" % new), book)
    print("refine: codebook %s -> %s (%d refined, %d dropped); round archived to %s (%s). Next: run.py code (recodes the whole corpus), "
          "then recode the held-out sample for the refined codes." % (old, new, len(ref), len(drop), arch.relative_to(W), ", ".join(moved)))
    return 0


# --------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="config.yaml or config.json (default: ./config.yaml)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--force", action="store_true")
    sub.add_parser("discovery-briefs")
    p = sub.add_parser("merge-readings")
    p.add_argument("--analyst")
    p = sub.add_parser("validate")
    p.add_argument("--stage", choices=["v0", "v1"], default="v0")
    p = sub.add_parser("apply-delta")
    p.add_argument("--analyst", required=True)
    p.add_argument("--base")
    p.add_argument("--delta")
    p.add_argument("--out")
    p = sub.add_parser("freeze")
    p.add_argument("--what", choices=["discovery", "coding"])
    p = sub.add_parser("reconcile-prepare")
    p.add_argument("--cond", choices=["lite", "full"], required=True)
    p = sub.add_parser("reconcile-apply")
    p.add_argument("--cond", choices=["lite", "full"], required=True)
    p.add_argument("--plan", help="a combined plan file relative to the workspace (default: combine the per-question plans)")
    p = sub.add_parser("approve")
    p.add_argument("--edits")
    p.add_argument("--candidate")
    p.add_argument("--version", default="1.0")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("code-prepare")
    p.add_argument("--batch-size", type=int)
    p = sub.add_parser("consensus")
    p.add_argument("--cond", choices=CONDITIONS)
    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true", help="machine-readable output (used by app.py)")
    sub.add_parser("dashboard")
    p = sub.add_parser("export-replies")
    p.add_argument("--to", required=True, help="folder for the recorded replies (relative to the config's folder)")
    p = sub.add_parser("refine")
    p.add_argument("--version", help="the new codebook version (default: minor version + 1)")
    import report as RP
    RP.add_parsers(sub)
    args = ap.parse_args(argv)
    init(args.config)
    RP.bind(sys.modules[__name__])
    cmds = {"prepare": cmd_prepare, "discovery-briefs": cmd_discovery_briefs, "merge-readings": cmd_merge_readings,
            "validate": cmd_validate, "apply-delta": cmd_apply_delta, "freeze": cmd_freeze,
            "reconcile-prepare": cmd_reconcile_prepare, "reconcile-apply": cmd_reconcile_apply, "approve": cmd_approve,
            "code-prepare": cmd_code_prepare, "consensus": cmd_consensus, "status": cmd_status, "refine": cmd_refine,
            "dashboard": cmd_dashboard, "export-replies": cmd_export_replies}
    cmds.update(RP.COMMANDS)
    return cmds[args.cmd](args) or 0


if __name__ == "__main__":
    sys.exit(main())
