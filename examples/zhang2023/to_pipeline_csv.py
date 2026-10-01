#!/usr/bin/env python3
"""
Make the pipeline's input from the 256 threads in data/: corpus.csv with uid, text, stratum, link and the
attribution columns (so_question_id, created, author).

`stratum` carries the paper's strata (tagged github-copilot or not x thread-length tercile, from
data/splits.json), so `council.py prepare` with this folder's config (seed 20260930, development share
0.25, blind pass 50, held out 60) draws the paper's development / evaluation split. Check that after
`prepare` with --check WORKSPACE.

  python3 examples/zhang2023/to_pipeline_csv.py                      # writes examples/zhang2023/corpus.csv
  python3 examples/zhang2023/to_pipeline_csv.py --check runs/zhang2023

With ZHANG_DEMO_ROOT set to the paper's experiment folder, it reads that folder's data/corpus.csv and
data/splits.json instead (the same threads).

The threads are Stack Overflow content under CC BY-SA (data/ATTRIBUTION.md). Standard library only.
"""
import argparse
import csv
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "corpus.csv"))
    ap.add_argument("--check", help="a prepared workspace whose data/splits.json is compared with the paper's split")
    a = ap.parse_args()
    if os.environ.get("ZHANG_DEMO_ROOT"):
        root = Path(os.environ["ZHANG_DEMO_ROOT"]).resolve()
        src, spf = root / "data" / "corpus.csv", root / "data" / "splits.json"
    else:
        src, spf = HERE / "data" / "threads.csv", HERE / "data" / "splits.json"
    csv.field_size_limit(10 ** 9)
    sp = json.loads(spf.read_text(encoding="utf-8"))
    if a.check:
        mine = json.loads((Path(a.check) / "data" / "splits.json").read_text())
        same_all = True
        for k in ("development", "evaluation", "blind_pass", "held_out"):
            same = set(mine.get(k, [])) == set(sp[k])
            same_all &= same
            print("%-12s %s (%d vs %d)" % (k, "identical" if same else "DIFFERENT", len(mine.get(k, [])), len(sp[k])))
        return 0 if same_all else 1
    with open(src, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    cols = ["uid", "text", "stratum", "link", "so_question_id", "created", "author"]
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({"uid": r["uid"], "text": r["text"], "stratum": sp["strata"][r["uid"]], "link": r["link"],
                        "so_question_id": r["so_question_id"], "created": r["created"], "author": r["author"]})
    print("wrote %s: %d threads" % (a.out, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
