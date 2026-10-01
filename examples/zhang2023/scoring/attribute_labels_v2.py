#!/usr/bin/env python3
# Copied from the paper's experiment (demo_v2/ground_truth/attribute_labels_v2.py) as a worked example. Only the
# path set-up changed: set ZHANG_DEMO_ROOT to the experiment folder. Outputs are written there, as in
# the experiment; copy the folder first if you want to keep the original results untouched.
"""
Attribute every row of Zhang et al.'s five constant-comparison sheets (functions, purposes,
benefits, limitations and challenges, expected features) to a thread of our corpus.

Their sheets carry no post id, so attribution is by text, with the matching rules of
../../demo/ground_truth/attribute_labels.py (reused here): exact normalised substring, else a
word n-gram score of at least 0.5 that beats the next thread by 0.2, against every segment and
every revision of the 256 surviving threads. `in_unit_text` says whether the coded text also
appears in our unit (the thread as of 18 June 2023).

Output: human_labels.csv (one line per attributed row and thread). Standard library + openpyxl.
"""
from __future__ import annotations
import csv, json, sys
from collections import Counter
from pathlib import Path

import os
# The experiment's folder (demo_v2 of the paper's project): set ZHANG_DEMO_ROOT to it. Data and model
# drivers are read from there; nothing is hard-coded to one machine.
ROOT = Path(os.environ["ZHANG_DEMO_ROOT"]).resolve()
HERE = ROOT / "ground_truth"
V2 = HERE.parent
OLD = V2.parent / "demo" / "ground_truth"
sys.path.insert(0, str(OLD))
from attribute_labels import norm, parts, thread_score, segments, score  # noqa: E402
from xlsx_read import read_sheet  # noqa: E402

SHEETS = {"Functions (SO)": "FU", "Purposes (SO)": "PU", "Benefits (SO)": "BE",
          "Limitations&Challenges (SO)": "LC", "Expected Features (SO)": "EF"}


def main():
    csv.field_size_limit(10**8)
    threads = json.loads((OLD / "so_threads.json").read_text())["threads"]
    segs = {q: [(k, norm(x)) for k, x in segments(t)] for q, t in threads.items() if t["found"]}
    corpus = {r["so_question_id"]: r for r in csv.DictReader((V2 / "data" / "corpus.csv").open())}
    unit_norm = {q: norm(r["text"]) for q, r in corpus.items()}
    out = []
    for sheet, dim in SHEETS.items():
        for i, r in enumerate(read_sheet(OLD / "Dataset (SO).xlsx", sheet)[1:], start=2):
            if not r or not r[0]:
                continue
            cat, file_, code, data = (str(x).strip() if x else "" for x in r[:4])
            pcs = parts(data)
            best = sorted(((sc, q, kinds) for q, ss in segs.items()
                           for sc, kinds in [thread_score(pcs, ss)] if sc > 0), key=lambda b: -b[0])
            second = best[1][0] if len(best) > 1 else 0.0
            if best and best[0][0] >= 0.999:
                hits, how = [b for b in best if b[0] >= 0.999], "exact"
            elif best and best[0][0] >= 0.5 and best[0][0] - second >= 0.2:
                hits, how = [best[0]], "fuzzy"
            else:
                hits, how = [], "unmatched"
            base = dict(sheet_row=i, dimension=dim, category=cat, coded_data=data.replace("\r", " "), match=how)
            if not hits:
                out.append({**base, "so_question_id": "", "uid": "", "segment": "", "in_unit_text": "",
                            "match_score": round(best[0][0], 3) if best else 0, "n_candidate_posts": 0})
            for sc, q, kinds in hits:
                order = ["title", "question_body", "question_comment", "answer", "answer_comment"]
                kinds = sorted(set(kinds), key=order.index) or ["?"]
                out.append({**base, "so_question_id": q, "uid": corpus[q]["uid"] if q in corpus else "",
                            "segment": "+".join(kinds),
                            "in_unit_text": any(score(pc, unit_norm[q]) >= 0.7 for pc in pcs) if q in unit_norm else "",
                            "match_score": round(sc, 3), "n_candidate_posts": len(hits)})
    cols = ["sheet_row", "dimension", "category", "so_question_id", "uid", "segment", "in_unit_text",
            "match", "match_score", "n_candidate_posts", "coded_data"]
    with (HERE / "human_labels.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    for dim in SHEETS.values():
        rs = [o for o in out if o["dimension"] == dim]
        print(dim, "rows", len({o["sheet_row"] for o in rs}), Counter(o["match"] for o in rs),
              "in our units", sum(1 for o in rs if o["uid"]), "text in unit", sum(1 for o in rs if o["in_unit_text"] is True))


if __name__ == "__main__":
    main()
