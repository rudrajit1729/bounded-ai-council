#!/usr/bin/env python3
"""
Reporting commands, reached through council.py:

  report          RESULTS.md (and dashboard.html) from every artifact in the workspace (counts at every stage, challenge
                  logs, review edits, reliability before and after adversaries, dropped codes, screening
                  recall, human-council agreement, cost)
  cost            calls, tokens and list-price cost per stage from logs/calls.jsonl -> results/costs.csv
  heldout-score   human-council agreement on the held-out sample (Cohen's kappa per code and pooled)
  retention       share of the researchers' own prior assignments retained by the council
  check-quotes    machine-check every quotation in a write-up as an exact substring of its source
  log-call        append a call to logs/calls.jsonl when an agent or a person answered a prompt by hand

Standard library only.
"""
from __future__ import annotations

import csv
import json
import re
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import reliability as R

M = None   # the council module, bound at start-up (cfg, W, helpers)


def bind(module):
    global M
    M = module


def add_parsers(sub):
    sub.add_parser("report")
    sub.add_parser("cost")
    p = sub.add_parser("heldout-score")
    p.add_argument("--labels", help="resolved researcher labels: CSV with uid + one 0/1 column per code id, or long uid,code "
                                    "(default: human/03_heldout_coding/resolved.csv in the workspace)")
    p.add_argument("--cond", choices=["L", "LJ", "LJA", "LA"])
    p = sub.add_parser("retention")
    p.add_argument("--human", required=True, help="the researchers' prior assignments: long CSV uid,code (approved code ids)")
    p.add_argument("--cond", choices=["L", "LJ", "LJA", "LA"])
    p = sub.add_parser("check-quotes")
    p.add_argument("file", help="a Markdown or text write-up; quotes are written \"...\" [UID] or “...” (UID)")
    p = sub.add_parser("log-call")
    for a in ("--stage", "--role", "--family", "--model", "--batch"):
        p.add_argument(a, default="-")
    p.add_argument("--input-tokens", type=int)
    p.add_argument("--output-tokens", type=int)
    p.add_argument("--seconds", type=float, default=0.0)
    p.add_argument("--inputs", nargs="*", default=[])
    p.add_argument("--outputs", nargs="*", default=[])
    p.add_argument("--reasoning", default="")
    p.add_argument("--note", default="answered by hand or by an agent")


# --------------------------------------------------------------------------- helpers
def labels_from_csv(path: Path, code_ids) -> dict:
    """{uid: set(codes)} from a wide (uid + 0/1 per code) or long (uid, code) CSV."""
    rows = M.read_csv(path)
    out = defaultdict(set)
    if rows and "code" in rows[0]:
        for r in rows:
            out[r["uid"].strip()]
            if r.get("code", "").strip():
                out[r["uid"].strip()].add(r["code"].strip())
        return dict(out)
    for r in rows:
        uid = (r.get("uid") or "").strip()
        if not uid:
            continue
        out[uid]
        for col, v in r.items():
            cid = (col or "").split(" ")[0].strip()
            if cid in code_ids and str(v).strip().lower() in ("1", "y", "yes", "x", "true"):
                out[uid].add(cid)
    return dict(out)


def consensus_sets(cond: str, retained_only=True) -> dict:
    res = M.W / "results" / cond
    f = res / ("consensus_retained.csv" if retained_only else "consensus.csv")
    if not f.exists():
        raise SystemExit("no %s; run `council.py consensus` first" % f.relative_to(M.W))
    out = defaultdict(set)
    for r in M.read_csv(f):
        out[r["uid"]].add(r["code"])
    return out


# --------------------------------------------------------------------------- held-out and retention
def cmd_heldout_score(args):
    cond = args.cond or M.primary_condition()
    book = M.approved_book()
    summ = M.read_json(M.W / "results" / cond / "summary.json")
    retained = summ["codes_retained"]
    lab = Path(args.labels) if args.labels else M.W / "human" / "03_heldout_coding" / "resolved.csv"
    if not lab.exists():
        raise SystemExit("no resolved labels at %s (the researchers' resolved held-out coding)" % lab)
    human = labels_from_csv(lab, {c["id"] for c in book["codes"]})
    held = set(M.splits().get("held_out") or [])
    units = [u for u in human if not held or u in held]
    if held and len(units) < len(human):
        print("   ! %d labelled units are not in the held-out sample and are ignored" % (len(human) - len(units)))
    council = consensus_sets(cond)
    per, hx, cx = [], [], []
    for cid in retained:
        h = [1 if cid in human[u] else 0 for u in units]
        c = [1 if cid in council.get(u, set()) else 0 for u in units]
        hx += h
        cx += c
        t = R.pair_table(h, c)
        per.append(OrderedDict([("code", cid), ("kappa", R.cohen_kappa(h, c)), ("n_human", sum(h)), ("n_council", sum(c)),
                                ("both", t["a"]), ("human_only", t["b"]), ("council_only", t["c"]), ("neither", t["d"])]))
    ks = [p["kappa"] for p in per if not R.nan(p["kappa"])]
    out = OrderedDict([("condition", cond), ("n_units", len(units)), ("n_codes_scored", len(retained)),
                       ("codes_not_scored_dropped_for_alpha", summ["codes_dropped_alpha_below_floor"] + summ["codes_alpha_undefined"]),
                       ("pooled_kappa", R.cohen_kappa(hx, cx)), ("median_kappa_per_code", R.median(ks)),
                       ("note", "Researchers' resolved labels against council consensus on retained codes; human labels for "
                                "dropped codes are not scored."),
                       ("per_code", per)])
    M.write_json(M.D("results", "human_council_agreement.json"), out)
    R.write_csv(M.W / "results" / "human_council_agreement.csv", per)
    print("heldout-score (%s): %d units, %d codes; pooled kappa %s; median per-code kappa %s"
          % (cond, len(units), len(retained), R.fmt(out["pooled_kappa"]), R.fmt(out["median_kappa_per_code"])))
    return 0


def cmd_retention(args):
    cond = args.cond or M.primary_condition()
    book = M.approved_book()
    human = labels_from_csv(Path(args.human), {c["id"] for c in book["codes"]})
    council = consensus_sets(cond, retained_only=False)
    pairs = [(u, c) for u, cs in human.items() for c in cs]
    kept = [p for p in pairs if p[1] in council.get(p[0], set())]
    by = defaultdict(lambda: [0, 0])
    for u, c in pairs:
        by[c][1] += 1
        by[c][0] += c in council.get(u, set())
    out = OrderedDict([("condition", cond), ("n_human_assignments", len(pairs)), ("n_retained", len(kept)),
                       ("retention_rate", round(len(kept) / len(pairs), 3) if pairs else None),
                       ("per_code", OrderedDict((c, "%d/%d" % tuple(v)) for c, v in sorted(by.items())))])
    M.write_json(M.D("results", "retention.json"), out)
    print("retention (%s): %d of %d researcher assignments retained (%s)" % (cond, len(kept), len(pairs), out["retention_rate"]))
    return 0


# --------------------------------------------------------------------------- quotations in a write-up
QUOTE = re.compile(r"(?:\"([^\"]{3,}?)\"|“([^”]{3,}?)”)\s*[\[(]([A-Za-z0-9_.:-]+)[\])]")


def cmd_check_quotes(args):
    corpus = M.load_corpus()
    text = Path(args.file).read_text(encoding="utf-8")
    bad, n = [], 0
    for m in QUOTE.finditer(text):
        q, uid = m.group(1) or m.group(2), m.group(3)
        if uid not in corpus:
            continue
        n += 1
        st = M.quote_status(q, corpus[uid]["text"])
        if st != "exact":
            bad.append((uid, st, q[:100]))
    for uid, st, q in bad:
        print("   FAIL %s (%s): %r" % (uid, st, q))
    print("check-quotes: %d quotations checked, %d not exact substrings of their source" % (n, len(bad)))
    return 1 if bad else 0


# --------------------------------------------------------------------------- calls and cost
def cmd_log_call(args):
    import models
    models.configure(M.cfg)
    hashes = lambda ps: {p: models.sha((M.W / p).read_bytes()) for p in ps if (M.W / p).exists()}
    models.log(args.stage, args.role, args.family, args.model, args.batch, args.seconds,
               {"input_tokens": args.input_tokens, "output_tokens": args.output_tokens, "reasoning_setting": args.reasoning,
                "model_reported": args.model}, hashes(args.inputs), hashes(args.outputs), "ok", args.note)
    print("logged %s / %s (%s, %s)" % (args.stage, args.role, args.family, args.model))
    return 0


def cost_rows():
    log = M.W / "logs" / "calls.jsonl"
    prices = M.cfg.d.get("prices") or {}
    agg = OrderedDict()
    if not log.exists():
        return []
    for line in log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("status") != "ok":
            continue
        key = (r["stage"], r.get("role_family", ""), r.get("model_id", ""))
        a = agg.setdefault(key, OrderedDict([("stage", key[0]), ("family", key[1]), ("model", key[2]), ("calls", 0),
                                             ("input_tokens", 0), ("output_tokens", 0), ("cost_usd", 0.0), ("priced", True)]))
        i, o = r.get("input_tokens") or 0, r.get("output_tokens") or 0
        a["calls"] += 1
        a["tokens_estimated"] = bool(a.get("tokens_estimated") or r.get("tokens_estimated"))
        a["input_tokens"] += i
        a["output_tokens"] += o
        pr = prices.get(r.get("model_id")) or prices.get(r.get("model_reported"))
        if pr:
            a["cost_usd"] += (i * float(pr[0]) + o * float(pr[1])) / 1e6
        elif r.get("cost_usd_reported"):
            a["cost_usd"] += float(r["cost_usd_reported"])
        else:
            a["priced"] = False
    rows = sorted(agg.values(), key=lambda a: (stage_rank(a["stage"]), a["family"], a["model"]))
    for a in rows:
        a["cost_usd"] = round(a["cost_usd"], 4)
    return rows


STAGES = ["discovery", "discovery-repair", "jev-leads", "discovery-adversary", "discovery-answer", "discovery-answer-repair",
          "reconcile", "reconcile-adversary", "reconcile-answer", "coding", "jev-screen", "coding-screened", "coding-adversary", "coding-answer"]


def stage_rank(stage: str) -> int:
    """Pipeline order of a stage name, so that tables do not depend on the order parallel calls finished."""
    return STAGES.index(stage) if stage in STAGES else len(STAGES)


def cmd_cost(args):
    rows = cost_rows()
    R.write_csv(M.D("results", "costs.csv"), rows)
    print("cost: %d stage/model rows; %d calls; $%.2f at configured list prices%s" % (
        len(rows), sum(r["calls"] for r in rows), sum(r["cost_usd"] for r in rows),
        "" if all(r["priced"] for r in rows) else " (some models have no price in config `prices`)"))
    return 0


# --------------------------------------------------------------------------- RESULTS.md
def tally(path: Path):
    t = OrderedDict([("ACCEPT", 0), ("REJECT", 0), ("PARTIAL", 0)])
    for a in M.rj(path).get("answers", []):
        k = (a.get("answer") or "").upper()
        t[k if k in t else "PARTIAL"] += 1
    return t


def cmd_report(args):
    cfg, W, rj = M.cfg, M.W, M.rj
    corpus = M.load_corpus()
    man = rj(W / "manifest.json")
    L = ["# Council run: results", ""]
    L.append("Generated %s by `council.py report` from the artifacts in `%s`. Mode: **%s**." % (
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), W.name, cfg.mode))
    fams = sorted(set(cfg.analysts.values()) | set(cfg.coders.values()))
    L.append("")
    L.append("The results dashboard for this run is [`dashboard.html`](dashboard.html) (open it in a browser; it works offline).")
    L.append("")
    L.append("**Vendor caveat.** Roles are assigned to %d model families (%s). Families can share errors, so agreement "
             "across them is evidence that the codebook was applied consistently, not that the codes are right. "
             "`logs/calls.jsonl` records the model id of every call." % (len(fams), ", ".join(fams)))
    L.append("")
    L.append("## 1. Run")
    L.append("")
    L.append("| | |\n|---|---|")
    L.append("| Units | %d%s |" % (len(corpus), " (with context)" if man.get("has_context") else ""))
    L.append("| Research questions | %s |" % "; ".join("%s %s" % (k, q["text"]) for k, q in cfg.rqs.items()))
    L.append("| Blocks | %s |" % man.get("n_blocks", 1))
    sp = M.splits()
    L.append("| Development / evaluation | %d / %d (seed %s) |" % (len(sp.get("development", [])), len(sp.get("evaluation", [])), sp.get("seed")))
    L.append("| Blind pass / held out | %d / %d |" % (len(sp.get("blind_pass", [])), len(sp.get("held_out", []))))
    L.append("| Analysts | %s |" % ", ".join("%s=%s" % kv for kv in cfg.analysts.items()))
    L.append("| Reconciler | %s |" % cfg.reconciler)
    L.append("| Coders | %s |" % ", ".join("%s=%s" % kv for kv in cfg.coders.items()))
    if cfg.full:
        L.append("| Discovery adversaries | %s |" % ", ".join("of %s=%s" % kv for kv in cfg.analyst_adversary.items()))
        L.append("| Reconciliation adversary | %s |" % cfg.recon_adversary)
        L.append("| Coding adversaries | %s |" % ", ".join("of %s=%s" % kv for kv in cfg.coder_adversary.items()))
        dm = cfg.d["decision_model"]
        L.append("| Decision model | %s |" % ("%s (%s)" % (dm.get("model"), dm.get("backend")) if cfg.decision_model_on else "off"))
    L.append("| Models | %s |" % "; ".join("%s: %s %s" % (f, (m or {}).get("backend"), (m or {}).get("model")) for f, m in (cfg.d.get("models") or {}).items()))
    L.append("| Thresholds | %s |" % ", ".join("%s=%s" % kv for kv in cfg.t.items()))
    L.append("| Data governance | %s |" % (cfg.d.get("data_governance") or "NOT RECORDED: state what left the machine, to which vendors, under which terms"))
    L.append("")

    # Stage 1
    L.append("## 2. Stage 1: discovery")
    L.append("")
    L.append("| Analyst | Family | Codes v0 (sem/lat/con) | Status v0 | Neither coded nor uncodeable v0 | Below floor v0 |" +
             (" Codes v1 | Status v1 | Adversary | Challenges | Accept/Reject/Partial | Quarantined | Adopted |" if cfg.full else ""))
    L.append("|---|---|---|---|---|---|" + ("---|---|---|---|---|---|---|" if cfg.full else ""))
    for A, fam in cfg.analysts.items():
        v0 = rj(W / "discovery" / "validation" / ("v0_analyst_%s.json" % A))
        s0 = v0.get("stats", {})
        lay = lambda s: "%s (%s)" % (s.get("n_codes", "-"), "/".join(str((s.get("n_by_layer") or {}).get(l, 0)) for l in M.LAYERS))
        row = "| %s | %s | %s | %s | %s | %s |" % (A, fam, lay(s0), v0.get("status", "-"), s0.get("n_units_neither_coded_nor_uncodeable", "-"), s0.get("n_below_floor", "-"))
        if cfg.full:
            v1 = rj(W / "discovery" / "validation" / ("v1_analyst_%s.json" % A))
            s1 = v1.get("stats", {})
            ch = rj(W / "discovery" / "challenges" / ("adversary_%s.json" % A))
            t = tally(W / "discovery" / "answers" / ("answer_%s.json" % A))
            row += " %s | %s | %s | %d | %d/%d/%d | %d | %s |" % (lay(s1), v1.get("status", "-"), cfg.analyst_adversary.get(A), len(ch.get("challenges", [])),
                                                                  t["ACCEPT"], t["REJECT"], t["PARTIAL"], len(ch.get("quarantined_codes") or []),
                                                                  s1.get("n_adopted_from_adversary", "-"))
        L.append(row)
    rep = rj(W / "discovery" / "validation" / "repairs.json")
    if rep:
        L.append("")
        L.append("Provenance repairs and completeness rounds per reading (units unaccounted before the completeness round): " +
                 "; ".join("%s: %s repairs, %s unaccounted" % (k, v.get("repairs"), v.get("units_unaccounted_before") or 0) for k, v in rep.items()))
    if cfg.full:
        L.append("")
        bytype, byaxis = defaultdict(int), defaultdict(int)
        for A in cfg.analysts:
            for c in rj(W / "discovery" / "challenges" / ("adversary_%s.json" % A)).get("challenges", []):
                bytype[c.get("type", "?")] += 1
                byaxis[c.get("axis", "?")] += 1
        L.append("Discovery challenges by type: %s; by axis: %s." % (", ".join("%s=%d" % kv for kv in sorted(bytype.items())) or "none",
                                                                     ", ".join("%s=%d" % kv for kv in sorted(byaxis.items())) or "none"))
        for A in cfg.analysts:
            g = rj(W / "discovery" / "jev" / ("grounding_%s.json" % A))
            o = rj(W / "discovery" / "jev" / ("omission_%s.json" % A))
            if g or o:
                L.append("- Decision-model leads for %s: %s of %s cited pairs below %s; %s uncited pairs at or above %s." % (
                    A, g.get("n_leads", "-"), g.get("n_pairs", "-"), cfg.t["grounding_lead_below"], o.get("n_leads", "-"), cfg.t["omission_lead_at_or_above"]))
    L.append("")

    # Stage 2
    L.append("## 3. Stage 2: reconciliation")
    L.append("")
    for cond in (["lite", "full"] if cfg.full else ["lite"]):
        b = rj(W / "codebooks" / ("candidate_%s.json" % cond))
        if not b:
            continue
        L.append("- **%s** (discovery %s): %d raw codes; %d groups; %d kept at the %d-unit floor (%d multi-analyst); %d dropped below the floor; "
                 "%d typed relations; %d raw codes in more than one group; %d quarantined candidates; %d apply errors." % (
                     cond.capitalize(), M.recon_stage(cond), b["n_raw_codes"], b["n_groups"], b["n_kept"], cfg.t["support_floor"], b["n_multi_analyst"],
                     b["n_dropped_below_floor"], b["n_relations"], b.get("n_raw_codes_in_multiple_groups", 0), b.get("n_quarantined", 0), len(b["errors"])))
        if b["dropped"]:
            L.append("  - Dropped below the floor: " + "; ".join("%s (%s, n=%d)" % (d["label"], d["rq"], d["n_units"]) for d in b["dropped"]))
        if cond == "full":
            chs = rj(W / "reconciliation" / "full" / "adversary_challenges.json").get("challenges", [])
            if chs:
                bt = defaultdict(int)
                for c in chs:
                    bt[c.get("type", "?")] += 1
                t = tally(W / "reconciliation" / "full" / "reconciler_answers.json")
                L.append("  - Reconciliation adversary (%s): %d challenges (%s); reconciler accepted %d, rejected %d, partly accepted %d." % (
                    cfg.recon_adversary, len(chs), ", ".join("%s=%d" % kv for kv in sorted(bt.items())), t["ACCEPT"], t["REJECT"], t["PARTIAL"]))
    L.append("")

    # Stage 3
    L.append("## 4. Stage 3: author review")
    L.append("")
    ap = rj(W / "codebooks" / "approved_codebook.json")
    if ap:
        rv = ap.get("review") or {}
        L.append("- Reviewed by: %s. %s" % (rv.get("reviewed_by") or "NOT RECORDED", rv.get("status_note", "")))
        L.append("- Blind pass: %d units (seed %s, %s). Researcher codes the council lacked: %s." % (
            len(sp.get("blind_pass", [])), sp.get("seed"), sp.get("blind_pass_note", ""), "; ".join(rv.get("blind_pass_codes_missing") or []) or "none recorded"))
        L.append("- Edits: %d (%s). Approved codes: %d; dropped at review: %d; quarantined candidates %d proposed, %d accepted. Version %s, closed %s." % (
            rv.get("n_edits", 0), ", ".join("%s=%d" % kv for kv in (rv.get("edits_by_type") or {}).items()), ap["n_approved"] + len(ap.get("dropped_low_alpha") or []),
            len(ap.get("dropped_at_review") or []), ap.get("n_quarantined_proposed", 0), ap.get("n_quarantined_accepted", 0),
            ((ap.get("low_alpha_rounds") or [{}])[0].get("from_version") or ap.get("version")), rv.get("closed_at")))
        for rd in ap.get("low_alpha_rounds") or []:
            L.append("- After the low-alpha decision: codebook %s (%s). The table shows the current version." % (rd.get("to_version"), "; ".join(
                "%s %s" % (x["id"], "refined" if x["op"] == "refine" else "dropped") for x in rd.get("log", []))))
        L.append("")
        L.append("| Id | RQ | Label | Analysts | Units at discovery | Layer origin |\n|---|---|---|---|---|---|")
        for c in ap["codes"]:
            L.append("| %s | %s | %s | %s | %d | %s |" % (c["id"], c.get("rq", ""), c["label"], "".join(c.get("analysts") or []) or "review",
                                                     c["n_units"], c.get("layer_origin", "")))
    else:
        L.append("Not yet approved.")
    L.append("")

    # Stage 4 and 5
    L.append("## 5. Stage 4: coding")
    L.append("")
    cm = rj(W / "coding" / "manifest.json")
    if cm:
        L.append("%d units in %d batches of up to %d; codebook version %s." % (cm["n_units"], cm["n_batches"], cm["batch_size"], cm["codebook_version"]))
    plan = rj(W / "coding" / "LJ" / "screening_plan.json")
    if plan:
        L.append("Screening: codes shown per unit %.1f of %d; %d audit pairs shown from the screened-out set (tau %s, top-k %s, audit share %s, seed %s)." % (
            plan["n_pairs_shown"] / max(1, len(plan["shown"])), len(ap.get("codes", [])), len(plan["audit_pairs"]),
            plan["tau_show"], plan["top_k"], plan["audit_share"], plan["seed"]))
    if cfg.full:
        L.append("")
        L.append("| Coder | Family | Adversary | Challenges | Types | Accept | Reject | Partial | Cells added/removed (v0 to v1) |\n|---|---|---|---|---|---|---|---|---|")
        diff = rj(W / "results" / "v0_v1_diff.json")
        for k, fam in cfg.coders.items():
            nf, bt = 0, defaultdict(int)
            t = OrderedDict([("ACCEPT", 0), ("REJECT", 0), ("PARTIAL", 0)])
            cdir = W / "coding" / M.adversary_cond() / "challenges"
            for p in sorted(cdir.glob("coder%s_batch*.json" % k)) if cdir.exists() else []:
                chs = M.read_json(p).get("challenges", [])
                nf += len(chs)
                for c in chs:
                    bt[c.get("type", "?")] += 1
                for kk, v in tally(cdir.parent / "answers" / p.name).items():
                    t[kk] += v
            pc = (diff.get("per_coder") or {}).get(k, {})
            L.append("| %s | %s | %s | %d | %s | %d | %d | %d | +%s / -%s |" % (k, fam, cfg.coder_adversary.get(k), nf, ", ".join("%s=%d" % kv for kv in sorted(bt.items())),
                                                                       t["ACCEPT"], t["REJECT"], t["PARTIAL"], pc.get("n_added", 0), pc.get("n_removed", 0)))
    L.append("")
    L.append("## 6. Stage 5: consensus and reliability")
    L.append("")
    conds = [c for c in ("L", "LJ", "LJA", "LA") if (W / "results" / c / "summary.json").exists()]
    names = {"L": "Lite coding (every code shown)" + (", v0 (independent coders)" if cfg.full and not cfg.decision_model_on else ""),
             "LJ": "screened coding, v0 (independent coders)", "LJA": "after coding adversaries, v1 (coder-adversary pipelines)",
             "LA": "after coding adversaries, v1 (coder-adversary pipelines)"}
    if conds:
        S = {c: M.read_json(W / "results" / c / "summary.json") for c in conds}
        t = cfg.t
        L.append("| | " + " | ".join("%s: %s" % (c, names[c]) for c in conds) + " |")
        L.append("|---|" + "---|" * len(conds))
        row = lambda lab, f: L.append("| %s | %s |" % (lab, " | ".join(f(S[c]) for c in conds)))
        row("Reliability units", lambda s: "%s (%d)" % (s["reliability_units"], s["n_reliability_units"]))
        row("Alpha median / min / max", lambda s: "%s / %s / %s" % (R.fmt(s["alpha_median"]), R.fmt(s["alpha_min"]), R.fmt(s["alpha_max"])))
        row("Codes below %s (held out of the results)" % t["alpha_drop"], lambda s: "%d (%s)" % (len(s["codes_dropped_alpha_below_floor"]), ", ".join(s["codes_dropped_alpha_below_floor"]) or "none"))
        row("Researchers' decision on them", lambda s: "; ".join("%s: %s" % (c, v.split(":")[0]) for c, v in (s.get("low_alpha_decisions") or {}).items()) or "none needed")
        row("Codes at or above %s" % t["alpha_high"], lambda s: "%d of %d" % (s["n_codes_alpha_at_or_above_%s" % t["alpha_high"]], s["n_codes"]))
        row("Codes with alpha undefined", lambda s: str(s["n_codes_alpha_undefined"]))
        row("Cross-family kappa median", lambda s: R.fmt(s["cross_family_kappa_median"]))
        row("Survival", lambda s: "%s" % s["survival"]["rate_pairs"])
        row("Issue units at consensus", lambda s: str(s["n_issue_units_consensus"]))
        row("Uncovered: any coder / consensus", lambda s: "%d / %d" % (s["n_uncovered_any_coder"], s["n_uncovered_consensus"]))
        row("Pairs pending the spot-check", lambda s: str(s.get("n_pairs_pending_spot_check", 0)))
        L.append("")
        prim = M.primary_condition() if M.primary_condition() in S else conds[-1]
        L.append("The results are those of **%s**. Codes dropped by the reliability rule are listed with their definitions and agreement "
                 "counts in `results/%s/reliability_report.md`; every code's figures are in `results/<condition>/reliability.csv`." % (prim, prim))
        if "L" in S and "LJ" in S and plan:
            lp = {(r["uid"], r["code"]) for r in M.read_csv(W / "results" / "L" / "consensus.csv") if r["code"] not in cfg.issue_codes and r["code"] != R.UNCOVERED}
            ljp = {(r["uid"], r["code"]) for r in M.read_csv(W / "results" / "LJ" / "consensus.csv")}
            ev = set(sp.get("evaluation") or [])
            lp = {p for p in lp if not ev or p[0] in ev}
            if lp:
                shown = sum(1 for u, c in lp if c in plan["shown"].get(u, []))
                L.append("")
                L.append("Screening recall against Lite coding (evaluation units): %d of %d Lite consensus pairs were shown to the coders (%.3f); "
                         "%d reached consensus under screening (%.3f)." % (shown, len(lp), shown / len(lp), len(lp & ljp), len(lp & ljp) / len(lp)))
        for rd in M.coding_rounds(ap):
            rs = rd["summary"]
            L.append("")
            L.append("**Earlier coding round (codebook %s, archived in `%s/`).** Alpha median %s (min %s, max %s); %d code(s) below %s. "
                     "The researchers' decisions: %s. The whole corpus was then recoded with codebook %s; the table above is that recode." % (
                         rd["from_version"], rd["archived_to"], R.fmt(rs.get("alpha_median")), R.fmt(rs.get("alpha_min")), R.fmt(rs.get("alpha_max")),
                         len(rs.get("codes_dropped_alpha_below_floor") or []), t["alpha_drop"],
                         "; ".join("%s %s (alpha %s) %s%s" % (x["id"], x["label"], R.fmt(float(x["alpha"])) if x["alpha"] else "n/a",
                                                             "refined" if x["op"] == "refine" else "dropped", (": " + x["reason"].rstrip(".")) if x["reason"] else "")
                                   for x in rd["decisions"]) or "none", rd["to_version"]))
        prev = W / "results" / prim / "prevalence.csv"
        if prev.exists():
            L.append("")
            L.append("### Prevalence (%s, retained codes)" % prim)
            L.append("")
            L.append("| Code | RQ | Label | Units | %% of %d | alpha |\n|---|---|---|---|---|---|" % S[prim]["prevalence_base"])
            for r in M.read_csv(prev):
                if r["status"] == "retained":
                    L.append("| %s | %s | %s | %s | %s | %s |" % (r["code"], r["rq"], r["label"], r["n_units"], r["pct_units"], (r["alpha"] or "n/a")[:5]))
    else:
        L.append("No coding results yet.")
    L.append("")
    hc = rj(W / "results" / "human_council_agreement.json")
    L.append("## 7. Human checks")
    L.append("")
    L.append("- Human-council agreement on the held-out sample: %s" % (
        "pooled kappa %s over %d units and %d codes (condition %s); median per-code kappa %s." % (
            R.fmt(hc["pooled_kappa"]), hc["n_units"], hc["n_codes_scored"], hc["condition"], R.fmt(hc["median_kappa_per_code"])) if hc else "not yet scored."))
    ret = rj(W / "results" / "retention.json")
    if ret:
        L.append("- Retention of the researchers' prior assignments: %s of %s (%s)." % (ret["n_retained"], ret["n_human_assignments"], ret["retention_rate"]))
    spn = W / "human" / "05_spot_check" / "decisions.csv"
    if spn.exists():
        sr = M.read_csv(spn)
        no = ["%s %s" % (r.get("uid"), r.get("code")) for r in sr if (r.get("keep") or "").strip().lower() in ("n", "no", "0", "false", "remove")]
        L.append("- Spot-check of rationales: %d rows checked in `human/05_spot_check/decisions.csv`; %d not kept%s." % (
            len(sr), len(no), (" (" + "; ".join(no) + "; recorded for the write-up, consensus unchanged)") if no else ""))
    else:
        L.append("- Spot-check of rationales: not yet recorded (packet: `human.py spot-check`).")
    dec = M.low_alpha_decisions()
    if dec:
        L.append("- Low-alpha decisions (`human/06_low_alpha/decisions.csv`): " + "; ".join(
            "%s %s%s" % (c, d["decision"], (" (" + d["decided_by"] + ")") if d.get("decided_by") else "") for c, d in dec.items()) + ".")
    L.append("")
    L.append("## 8. Calls, tokens and cost")
    L.append("")
    rows = cost_rows()
    if rows:
        L.append("| Stage | Family | Model | Calls | Input tokens | Output tokens | Cost (USD) |\n|---|---|---|---|---|---|---|")
        for r in rows:
            L.append("| %s | %s | %s | %d | %s | %s | %s |" % (r["stage"], r["family"], r["model"], r["calls"], "{:,}".format(r["input_tokens"]),
                                                          "{:,}".format(r["output_tokens"]), ("%.2f" % r["cost_usd"]) if r["priced"] else "unpriced"))
        for lab, sel in (("Model calls", lambda r: r["family"] != "decision-model"), ("Decision-model requests", lambda r: r["family"] == "decision-model")):
            rr = [r for r in rows if sel(r)]
            if rr:
                L.append("| %s | | | %d | %s | %s | %.2f |" % (lab, sum(r["calls"] for r in rr), "{:,}".format(sum(r["input_tokens"] for r in rr)),
                                                            "{:,}".format(sum(r["output_tokens"] for r in rr)), sum(r["cost_usd"] for r in rr)))
        L.append("| **Total** | | | %d | %s | %s | %.2f |" % (sum(r["calls"] for r in rows), "{:,}".format(sum(r["input_tokens"] for r in rows)),
                                                         "{:,}".format(sum(r["output_tokens"] for r in rows)), sum(r["cost_usd"] for r in rows)))
        if any(r.get("tokens_estimated") for r in rows):
            L.append("")
            L.append("Token counts of calls answered by hand (`manual`) or replayed (`replay`) are estimated from characters (about 4 per token).")
    else:
        L.append("No call log.")
    L.append("")
    fz = rj(W / "logs" / "freeze.json")
    L.append("## 9. Frozen files")
    L.append("")
    L.append("%d pre-adversary files frozen (read-only, sha256 in `logs/freeze.json`)." % len(fz) if fz else "No freeze log.")
    L.append("")
    (W / "RESULTS.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("report: %s (%d lines)" % (W / "RESULTS.md", len(L)))
    import dashboard as DB
    DB.bind(M)
    print("dashboard: %s" % DB.write())
    return 0


COMMANDS = {"report": cmd_report, "cost": cmd_cost, "heldout-score": cmd_heldout_score, "retention": cmd_retention,
            "check-quotes": cmd_check_quotes, "log-call": cmd_log_call}
