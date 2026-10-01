#!/usr/bin/env python3
# Copied from the paper's experiment (demo_v2/ground_truth/coding_scores.py) as a worked example. Only the
# path set-up changed: set ZHANG_DEMO_ROOT to the experiment folder. Outputs are written there, as in
# the experiment; copy the folder first if you want to keep the original results untouched.
"""
Final scores for every coding condition (ANALYSIS_PLAN section 4), on the evaluation threads.

  agreement with Zhang et al.  (primary ground truth: labels whose text points to one thread)
    recall     Zhang labels reached by a consensus code mapped to that label's category / labels
    precision  consensus (thread, code) pairs whose code maps to a category and whose thread carries a
               label in that code's own question, that match a label on the thread / such pairs
               (same-question precision); the all-labels variant is reported beside it
    95% intervals: 1,000 bootstrap resamples of threads, seed 20260930
  reliability     per-code Krippendorff's alpha from results/<cond>_eval/summary.json
  screening       share of the Lite consensus pairs that screening showed to the coders, and that the
                  screened (LJ) consensus reached
  cost            tokens and list-price cost from logs/calls.jsonl

  python3 coding_scores.py [mapping.json]
"""
from __future__ import annotations
import csv, json, random, sys
from collections import defaultdict
from pathlib import Path

import os
# The experiment's folder (demo_v2 of the paper's project): set ZHANG_DEMO_ROOT to it. Data and model
# drivers are read from there; nothing is hard-coded to one machine.
ROOT = Path(os.environ["ZHANG_DEMO_ROOT"]).resolve()
HERE = ROOT / "ground_truth"
V2 = HERE.parent
import os
FULL = V2 / "runs" / ("full_q" if os.environ.get("COUNCIL_VARIANT") == "q" else "full")
SEGMENTS = ({"title", "question_body", "title+question_body"} if os.environ.get("COUNCIL_VARIANT") == "q" else None)
COND = ["L", "L_rep2", "L_rep3", "LJ", "LJA"]
NAMES = {"L": "Lite", "L_rep2": "Lite, rerun 2", "L_rep3": "Lite, rerun 3", "LJ": "Lite + Jev screening",
         "LJA": "Full (screening + coding adversaries)"}
DIM = {"RQ1.4": "FU", "RQ1.5": "PU", "RQ2.1": "BE", "RQ2.2": "LC", "RQ2.3": "EF"}
PRICE = {  # USD per million tokens (input, output), checked 1 October 2026.
    # Claude: Anthropic API reference (cached 25 September 2026); 1M context is the default, no surcharge.
    # GPT-5.6: developers.openai.com/api/docs/pricing, checked 30 September 2026 (Sol at the promotional $4/$20 from 21 August 2026); no call here exceeded the 272K-token input tier.
    # Jev: docs.typesafe.ai/models ($0.042 per million input tokens, output free).
    "claude-opus-5": (5, 25), "gemini-3.7-flash": (0.75, 3.75), "gpt-5.6-terra": (2.0, 12.0), "gpt-5.6-sol": (4.0, 20.0), "jev-1.13.0": (0.042, 0), "jev-latest": (0.042, 0)}


def load_labels():
    zc = {c["name"].strip().lower(): c["id"] for c in json.loads((HERE / "zhang_codebook_v2.json").read_text())["categories"]}
    ev = set(json.loads((V2 / "data" / "splits.json").read_text())["evaluation"])
    lab = defaultdict(set)
    for r in csv.DictReader((HERE / "human_labels.csv").open()):
        if r["uid"] in ev and r["n_candidate_posts"] == "1" and (SEGMENTS is None or r["segment"] in SEGMENTS):
            lab[r["uid"]].add(zc[r["category"].strip().lower().replace("  ", " ")])
    return lab, ev


def consensus_pairs(cond, ev):
    p = FULL / "results" / cond / "consensus.csv"
    if not p.exists():
        return None
    return [(r["uid"], r["code"]) for r in csv.DictReader(p.open()) if r["uid"] in ev and r["code"].startswith("T")]


def score(pairs, mp, rq, lab, units):
    labels = {(u, c) for u in units for c in lab.get(u, ())}
    reached = {(u, cat) for u, cid in pairs if u in units for cat in mp.get(cid, ())}
    hit = len(labels & reached)
    sp = [(u, cid) for u, cid in pairs if u in units and mp.get(cid) and lab.get(u)]
    ag = sum(1 for u, cid in sp if mp[cid] & lab[u])
    sq = [(u, cid) for u, cid in sp if any(x[:2] == DIM.get(rq.get(cid)) for x in lab[u])]
    agq = sum(1 for u, cid in sq if mp[cid] & lab[u])
    R = hit / len(labels) if labels else 0
    P = ag / len(sp) if sp else 0
    Pq = agq / len(sq) if sq else 0
    f = lambda a, b: 2 * a * b / (a + b) if a + b else 0
    return {"recall": R, "precision": P, "precision_same_q": Pq, "f1": f(R, P), "f1_same_q": f(R, Pq),
            "reached": f"{hit}/{len(labels)}", "agree_same_q": f"{agq}/{len(sq)}"}


def boot(pairs, mp, rq, lab, ev, n=1000):
    units = sorted(u for u in ev if lab.get(u))
    rng = random.Random(20260930)
    by_u = defaultdict(list)
    for u, c in pairs:
        by_u[u].append(c)
    keys = ["recall", "precision_same_q", "f1_same_q"]
    vals = {k: [] for k in keys}
    for _ in range(n):
        samp = [rng.choice(units) for _ in units]
        # resample threads with replacement: relabel duplicates so each copy counts
        lab2, pairs2 = {}, []
        for i, u in enumerate(samp):
            key = f"{u}#{i}"
            lab2[key] = lab[u]
            pairs2 += [(key, c) for c in by_u.get(u, [])]
        s = score(pairs2, mp, rq, lab2, set(lab2))
        for k in keys:
            vals[k].append(s[k])
    return {k: (sorted(v)[25], sorted(v)[974]) for k, v in vals.items()}


def main():
    mpath = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "mapping_approved.json"
    mp = {m["code_id"]: {c["id"] for c in m["categories"]} for m in json.loads(mpath.read_text())["mapping"]}
    book = json.loads((FULL / "codebooks" / "approved_codebook.json").read_text())
    rq = {c["id"]: c.get("rq", "") for c in book["codes"]}
    lab, ev = load_labels()
    out = {"mapping": mpath.name, "codebook_version": book.get("version"), "conditions": {}}
    for cond in COND:
        pairs = consensus_pairs(cond, ev)
        if pairs is None:
            continue
        s = score(pairs, mp, rq, lab, ev)
        s["ci95"] = boot(pairs, mp, rq, lab, ev)
        summ = FULL / "results" / f"{cond}_eval" / "summary.json"
        if summ.exists():
            sm = json.loads(summ.read_text())
            s["alpha"] = {k: sm.get(k) for k in ("alpha_median", "alpha_min", "n_codes_alpha_below_0.67",
                                                  "n_codes_alpha_at_or_above_0.80", "n_codes")}
            s["survival"] = sm.get("survival", {}).get("rate_pairs")
        out["conditions"][cond] = s
    # screening recall against the unscreened Lite consensus
    plan = FULL / "coding" / "LJ" / "screening_plan.json"
    if plan.exists() and consensus_pairs("L", ev) is not None:
        shown = json.loads(plan.read_text())["shown"]
        lpairs = set(consensus_pairs("L", ev))
        ljp = set(consensus_pairs("LJ", ev) or [])
        out["screening"] = {
            "share_of_Lite_consensus_pairs_shown": round(sum(1 for u, c in lpairs if c in shown.get(u, [])) / len(lpairs), 3),
            "share_of_Lite_consensus_pairs_kept_in_LJ": round(len(lpairs & ljp) / len(lpairs), 3),
            "codes_shown_per_thread": round(sum(len(v) for v in shown.values()) / len(shown), 1),
            "codes_in_book": len(book["codes"])}
    # cost by condition from the call log
    cost = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0, "usd": 0.0})
    # both workspaces share one call log: a call belongs to this workspace when one of its input files is
    # all its input files are files of this workspace (by hash); Jev screening calls by the window ending at screen.json's write
    import hashlib
    from datetime import datetime, timezone, timedelta
    mine = {hashlib.sha256(f.read_bytes()).hexdigest() for d in ("coding", "briefs")
            for f in (FULL / d).rglob("*") if f.is_file()}
    scr = FULL / "coding" / "jev" / "screen.json"
    t1 = datetime.fromtimestamp(scr.stat().st_mtime, timezone.utc) if scr.exists() else None
    for line in (V2 / "logs" / "calls.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r.get("status") != "ok":
            continue
        if r["stage"] == "jev-screen":
            ts = datetime.fromisoformat(r["ts"])
            if not t1 or not (t1 - timedelta(minutes=30) <= ts <= t1 + timedelta(minutes=1)):
                continue
        elif not r.get("inputs_sha256") or not set(r["inputs_sha256"].values()) <= mine:
            continue
        st = r["stage"]
        key = (st.replace("coding-", "") if st.startswith("coding-") and st not in ("coding-adversary", "coding-answer")
               else "LJA" if st in ("coding-adversary", "coding-answer") else "jev-screen" if st == "jev-screen" else None)
        if not key:
            continue
        pi, po = PRICE.get(r.get("model_id"), (0, 0))
        i, o = r.get("input_tokens") or 0, r.get("output_tokens") or 0
        c = cost[key]
        c["calls"] += 1; c["in"] += i; c["out"] += o; c["usd"] += (i * pi + o * po) / 1e6
    out["coding_cost"] = {k: {**v, "usd": round(v["usd"], 2)} for k, v in cost.items()}
    (HERE / "coding_scores.json").write_text(json.dumps(out, indent=1))
    print(f"{'condition':40s} {'recall':>8s} {'prec(q)':>8s} {'F1(q)':>7s} {'prec(all)':>9s} {'alpha med':>9s} {'min':>6s} {'<.67':>5s}")
    for cond, s in out["conditions"].items():
        a = s.get("alpha", {})
        print(f"{NAMES[cond]:40s} {s['recall']:8.3f} {s['precision_same_q']:8.3f} {s['f1_same_q']:7.3f} {s['precision']:9.3f} "
              f"{(a.get('alpha_median') or 0):9.3f} {(a.get('alpha_min') or 0):6.2f} {a.get('n_codes_alpha_below_0.67', '')!s:>5s}"
              f"   recall CI {s['ci95']['recall'][0]:.2f}-{s['ci95']['recall'][1]:.2f}")
    print(json.dumps({k: out.get(k) for k in ("screening", "coding_cost")}, indent=1))


if __name__ == "__main__":
    main()
