#!/usr/bin/env python3
# Copied from the paper's experiment (demo_v2/ground_truth/codebook_scores.py) as a worked example. Only the
# path set-up changed: set ZHANG_DEMO_ROOT to the experiment folder. Outputs are written there, as in
# the experiment; copy the folder first if you want to keep the original results untouched.
"""
Codebook-stage agreement with Zhang et al. (evaluation threads, unique-attribution labels). A code is
credited on the threads it cites as evidence. Rows: every code, and the weakly supported codes removed
(median decision-model support < 0.5, support_<name>.json).
  python3 codebook_scores.py
"""
import csv, json
from collections import defaultdict
from pathlib import Path
import os
# The experiment's folder (demo_v2 of the paper's project): set ZHANG_DEMO_ROOT to it. Data and model
# drivers are read from there; nothing is hard-coded to one machine.
ROOT = Path(os.environ["ZHANG_DEMO_ROOT"]).resolve()
HERE = ROOT / "ground_truth"
RUNS = HERE.parent / "runs"
DIM = {"RQ1.4": "FU", "RQ1.5": "PU", "RQ2.1": "BE", "RQ2.2": "LC", "RQ2.3": "EF"}
Q = {"title", "question_body", "title+question_body"}
import sys
DEF = len(sys.argv) > 1 and sys.argv[1] == "defensible"   # mappings under the defensible rule (map_defensible.py)
ROWS = [("Lite candidate", RUNS / "lite/codebooks/candidate_codebook.json", "mapping_claude_lite_candidate.json", "support_lite.json"),
        ("Full candidate", RUNS / "full/codebooks/candidate_codebook.json", "mapping_claude_full_candidate_rereview.json", "support_full.json"),
        ("Reviewed (v1.2)", RUNS / "full/codebooks/approved_codebook_v1.2.json", "mapping_v1.2.json", "support_v1.2.json")]
ev = set(json.loads((HERE.parent / "data/splits.json").read_text())["evaluation"])
zc = {c["name"].strip().lower(): c["id"] for c in json.loads((HERE / "zhang_codebook_v2.json").read_text())["categories"]}
rows = list(csv.DictReader((HERE / "human_labels.csv").open()))


def labels(seg):
    lab = defaultdict(set)
    for r in rows:
        if r["uid"] in ev and r["n_candidate_posts"] == "1" and (seg is None or r["segment"] in seg):
            lab[r["uid"]].add(zc[r["category"].strip().lower().replace("  ", " ")])
    return lab


def score(codes, mp, lab):
    rq = {c["id"]: c.get("rq", "") for c in codes}
    pairs = [(u, c["id"]) for c in codes for u in c["units"] if u in ev]
    gold = {(u, k) for u, ks in lab.items() for k in ks}
    hit = gold & {(u, k) for u, c in pairs for k in mp.get(c, ())}
    sq = [(u, c) for u, c in pairs if mp.get(c) and any(x[:2] == DIM.get(rq[c]) for x in lab.get(u, ()))]
    ag = sum(1 for u, c in sq if mp[c] & lab[u])
    R, P = len(hit) / len(gold), ag / len(sq)
    return R, P, 2 * R * P / (R + P), f"{len(hit)}/{len(gold)}", f"{ag}/{len(sq)}"


if DEF:
    ROWS = [(n, b, {"Lite candidate": "mapping_def_lite.json", "Full candidate": "mapping_def_full.json",
                    "Reviewed (v1.2)": "mapping_def_v1.2.json"}[n], sp) for n, b, _, sp in ROWS]
out = []
print(f"{'codebook':34s} {'labels':13s} {'codes':>5s} {'recall':>7s} {'prec':>7s} {'F1':>6s}  reached  agreeing")
for name, bp, mpath, spath in ROWS:
    book = json.loads(bp.read_text())
    mp = {m["code_id"]: {c["id"] for c in m["categories"]} for m in json.loads((HERE / mpath).read_text())["mapping"]}
    med = json.loads((HERE / spath).read_text())["median"]
    print(f"  [{mpath}: {sum(len(v) for v in mp.values()) / len(mp):.2f} categories per code, "
          f"{sum(1 for v in mp.values() if not v)} codes unmapped]")
    for filt in (False, True):
        codes = [c for c in book["codes"] if not filt or med.get(c["id"], 0) >= 0.5]
        for lname, seg in (("whole thread", None), ("question text", Q)):
            R, P, F, a, b = score(codes, mp, labels(seg))
            n = name + (", weak removed" if filt else "")
            out.append({"codebook": n, "labels": lname, "codes": len(codes), "recall": round(R, 3), "precision": round(P, 3), "f1": round(F, 3), "reached": a, "agreeing": b})
            print(f"{n:34s} {lname:13s} {len(codes):5d} {R:7.3f} {P:7.3f} {F:6.3f}  {a:8s} {b}")
(HERE / ("codebook_scores_defensible.json" if DEF else "codebook_scores.json")).write_text(json.dumps(out, indent=1))
