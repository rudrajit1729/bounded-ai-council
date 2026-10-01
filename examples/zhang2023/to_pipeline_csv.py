#!/usr/bin/env python3
"""
Convert the experiment's corpus (demo_v2/data/corpus.csv, built by demo_v2/build_corpus.py from Zhang et
al.'s post list) into the pipeline's input format: uid, text, stratum, link, plus the attribution columns.

`stratum` carries the experiment's strata (tagged github-copilot or not x thread-length tercile, from
demo_v2/data/splits.json), so `council.py prepare` with this folder's config.yaml (seed 20260930,
development share 0.25, blind pass 50, held out 60) draws the experiment's development / evaluation split.
The script checks that after `prepare` if you pass --check WORKSPACE.

  ZHANG_DEMO_ROOT=/path/to/demo_v2 python3 to_pipeline_csv.py [--out corpus.csv] [--check runs/zhang2023]

The corpus is Stack Overflow content under CC BY-SA (attribution columns kept). Standard library only.
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
    ap.add_argument("--check", help="a prepared workspace whose data/splits.json is compared with the experiment's")
    a = ap.parse_args()
    root = Path(os.environ["ZHANG_DEMO_ROOT"]).resolve()
    csv.field_size_limit(10 ** 9)
    rows = list(csv.DictReader((root / "data" / "corpus.csv").open(encoding="utf-8")))
    sp = json.loads((root / "data" / "splits.json").read_text())
    if a.check:
        mine = json.loads((Path(a.check) / "data" / "splits.json").read_text())
        for k in ("development", "evaluation", "blind_pass", "held_out"):
            same = set(mine.get(k, [])) == set(sp[k])
            print("%-12s %s (%d vs %d)" % (k, "identical" if same else "DIFFERENT", len(mine.get(k, [])), len(sp[k])))
        return
    cols = ["uid", "text", "stratum", "link", "so_question_id", "created", "author"]
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({"uid": r["uid"], "text": r["text"], "stratum": sp["strata"][r["uid"]], "link": r["link"],
                        "so_question_id": r["so_question_id"], "created": r["created"], "author": r["author"]})
    print("wrote %s: %d units" % (a.out, len(rows)))


if __name__ == "__main__":
    main()
