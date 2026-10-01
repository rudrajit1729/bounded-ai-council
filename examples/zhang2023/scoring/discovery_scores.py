#!/usr/bin/env python3
# Copied from the paper's experiment (demo_v2/ground_truth/discovery_scores.py) as a worked example. Only the
# path set-up changed: set ZHANG_DEMO_ROOT to the experiment folder. Outputs are written there, as in
# the experiment; copy the folder first if you want to keep the original results untouched.
"""
Discovery-stage agreement with Zhang et al. for one codebook (evaluation threads; primary ground
truth = labels whose text points to exactly one thread). A code "assigns" itself to the threads it
cites as evidence (discovery does not code every thread, so these are conservative).
  recall    = Zhang labels reached by a cited code mapped to that label's category / Zhang labels
  precision = cited (thread, code) pairs whose code maps to at least one category and whose thread
              carries at least one Zhang label, that match a label on that thread / such pairs
  python3 discovery_scores.py <codebook.json> <mapping.json>
"""
import csv, json, sys
from collections import defaultdict
from pathlib import Path
import os
# The experiment's folder (demo_v2 of the paper's project): set ZHANG_DEMO_ROOT to it. Data and model
# drivers are read from there; nothing is hard-coded to one machine.
ROOT = Path(os.environ["ZHANG_DEMO_ROOT"]).resolve()
HERE = ROOT / "ground_truth"
book = json.loads(Path(sys.argv[1]).read_text())
mp = {m["code_id"]: {c["id"] for c in m["categories"]} for m in json.loads(Path(sys.argv[2]).read_text())["mapping"]}
zc = {c["name"].strip().lower(): c["id"] for c in json.loads((HERE / "zhang_codebook_v2.json").read_text())["categories"]}
ev = set(json.loads((HERE.parent / "data" / "splits.json").read_text())["evaluation"])
lab = defaultdict(set)
for r in csv.DictReader((HERE / "human_labels.csv").open()):
    if r["uid"] in ev and r["n_candidate_posts"] == "1":
        lab[r["uid"]].add(zc[r["category"].strip().lower().replace("  ", " ")])
pairs = [(u, c["id"]) for c in book["codes"] for u in c["units"] if u in ev]
reached = {(u, cat) for u, cid in pairs for cat in mp.get(cid, ())}
labels = {(u, cat) for u, cs in lab.items() for cat in cs}
hit = labels & reached
scor = [(u, cid) for u, cid in pairs if mp.get(cid) and lab.get(u)]
agree = [p for p in scor if mp[p[1]] & lab[p[0]]]
dims = defaultdict(lambda: [0, 0])
for u, cat in labels:
    dims[cat[:2]][1] += 1; dims[cat[:2]][0] += (u, cat) in hit
R, P = len(hit) / len(labels), len(agree) / len(scor)
# same-question precision: a council code is scored only on threads where Zhang et al. labelled
# that same question (their extraction recorded only what posters stated, per question)
DIM = {"RQ1.4": "FU", "RQ1.5": "PU", "RQ2.1": "BE", "RQ2.2": "LC", "RQ2.3": "EF"}
rq = {c["id"]: c.get("rq", "") for c in book["codes"]}
scor_q = [(u, cid) for u, cid in pairs if mp.get(cid) and any(x[:2] == DIM.get(rq[cid]) for x in lab.get(u, ()))]
agree_q = [p for p in scor_q if mp[p[1]] & lab[p[0]]]
Pq = len(agree_q) / len(scor_q) if scor_q else 0
print(json.dumps({"codes": len(book["codes"]), "recall": round(R, 3), "precision": round(P, 3), "f1": round(2 * R * P / (R + P), 3),
                  "reached": f"{len(hit)}/{len(labels)}", "agreeing_pairs": f"{len(agree)}/{len(scor)}",
                  "precision_same_question": round(Pq, 3), "f1_same_question": round(2 * R * Pq / (R + Pq), 3),
                  "agreeing_pairs_same_question": f"{len(agree_q)}/{len(scor_q)}",
                  "by_dimension": {d: f"{a}/{b}" for d, (a, b) in sorted(dims.items())}}))
