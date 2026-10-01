#!/usr/bin/env python3
# Copied from the paper's experiment (demo_v2/ground_truth/support_scores.py) as a worked example. Only the
# path set-up changed: set ZHANG_DEMO_ROOT to the experiment folder. Outputs are written there, as in
# the experiment; copy the folder first if you want to keep the original results untouched.
"""
Support of each code in a codebook: the decision model's probability that each thread the code cites
meets the code's definition (same question as Stage 4 screening, whole-thread text). A code is weakly
supported when the median over its cited threads is below 0.5.
  python3 support_scores.py <codebook.json> <out.json>
"""
import csv, json, statistics, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
# The experiment's folder (demo_v2 of the paper's project): set ZHANG_DEMO_ROOT to it. Data and model
# drivers are read from there; nothing is hard-coded to one machine.
ROOT = Path(os.environ["ZHANG_DEMO_ROOT"]).resolve()
HERE = ROOT / "ground_truth"
sys.path.insert(0, str(HERE.parent))
import models  # noqa: E402
from run import SCREEN_Q, code_view  # noqa: E402

csv.field_size_limit(10**8)
book = json.loads(Path(sys.argv[1]).read_text())
corpus = {r["uid"]: r["text"] for r in csv.DictReader((HERE.parent / "data" / "corpus.csv").open())}
by_unit = {}
for c in book["codes"]:
    for u in c["units"]:
        by_unit.setdefault(u, []).append(c)


def one(u):
    qs = {c["id"]: {"type": "noul", "instructions": {"code": code_view(c), "question": SCREEN_Q}} for c in by_unit[u]}
    return u, models.jev({"thread": corpus[u]}, qs, stage="support", role="support", batch=u)


with ThreadPoolExecutor(8) as ex:
    res = dict(ex.map(one, sorted(by_unit)))
sup = {c["id"]: {u: res[u].get(c["id"]) for u in c["units"]} for c in book["codes"]}
med = {k: statistics.median([p for p in v.values() if p is not None] or [0]) for k, v in sup.items()}
Path(sys.argv[2]).write_text(json.dumps({"question": SCREEN_Q, "median": med, "per_unit": sup}, indent=1))
print(f"{len(med)} codes; weakly supported (median < 0.5): {sum(m < 0.5 for m in med.values())}")
