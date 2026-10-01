#!/usr/bin/env python3
"""
The offline demo: the whole procedure, in Full mode, on a tiny invented corpus, with no model and no
network. Every model and decision-model call is answered from examples/tiny/replay/ (the `replay`
backend), and every researchers' step is filled with the dummy files in examples/tiny/human_demo/
(fictional reviewers DEMO-A and DEMO-B), copied in where the procedure stops for the researchers.

    python3 pipeline/demo.py            # runs into examples/tiny/workspace/ (starts afresh if it exists)
    python3 pipeline/demo.py --keep     # keep an existing workspace and only run what is missing

The demo runs the same commands a user or a coding agent runs (AGENTS.md), one after the other, and
prints each one. At the end it prints where RESULTS.md, the results dashboard and the review
dashboard are.

Standard library only.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PIPE = Path(__file__).resolve().parent
REPO = PIPE.parent
TINY = REPO / "examples" / "tiny"
HUMAN = TINY / "human_demo"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(TINY / "config.yaml"), help="the demo config (default: examples/tiny/config.yaml)")
    ap.add_argument("--keep", action="store_true", help="do not delete an existing demo workspace first")
    a = ap.parse_args(argv)
    cfg = Path(a.config).resolve()
    sys.path.insert(0, str(PIPE))
    import config as C
    ws = C.load(cfg).workspace
    if ws.exists() and not a.keep:
        if ws.parent != cfg.parent or ws.name in ("", ".", ".."):
            raise SystemExit("refusing to delete %s: the demo workspace must be a folder next to its config" % ws)
        print("demo: removing the previous demo workspace %s" % ws)
        for f in ws.rglob("*"):
            if f.is_file():
                f.chmod(0o644)
        shutil.rmtree(ws)

    def run(script, *args):
        cmd = [sys.executable, str(PIPE / script), "--config", str(cfg)] + list(args)
        print("\n$ python3 pipeline/%s --config %s %s" % (script, cfg.relative_to(REPO) if cfg.is_relative_to(REPO) else cfg, " ".join(args)), flush=True)
        p = subprocess.run(cmd, cwd=str(REPO))
        if p.returncode != 0:
            raise SystemExit("demo: the command above failed (exit %d)" % p.returncode)

    def human(note, files):
        print("\n# RESEARCHERS (simulated with dummy files from examples/tiny/human_demo/): %s" % note, flush=True)
        for src, dest in files:
            d = ws / dest
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(HUMAN / src, d)
            print("#   %s -> %s" % (src, dest))

    run("council.py", "status")
    run("council.py", "prepare")
    run("human.py", "blind-pass")
    human("STOP 1, the blind pass, returned by DEMO-A and DEMO-B",
          [("blind_pass_DEMO-A.csv", "human/01_blind_pass/returned/blind_pass_DEMO-A.csv"),
           ("blind_pass_DEMO-B.csv", "human/01_blind_pass/returned/blind_pass_DEMO-B.csv")])
    run("run.py", "discovery")
    run("run.py", "discovery-adversary")
    run("run.py", "reconcile")
    run("human.py", "review-dashboard")
    human("STOP 2, author review: each reviewer's downloaded decisions",
          [("review_DEMO-A.json", "human/02_author_review/returned/review_DEMO-A.json"),
           ("review_DEMO-B.json", "human/02_author_review/returned/review_DEMO-B.json")])
    run("human.py", "review-to-edits")
    human("the negotiated edit log", [("review_edits.json", "codebooks/review_edits.json")])
    run("council.py", "approve")
    run("human.py", "heldout-packet")
    human("STOP 3, held-out coding, resolved", [("heldout_resolved.csv", "human/03_heldout_coding/resolved.csv")])
    run("run.py", "code")
    run("human.py", "spot-check")
    human("STOP 4, spot-check decisions", [("spot_check_decisions.csv", "human/05_spot_check/decisions.csv")])
    run("council.py", "consensus")
    run("human.py", "low-alpha")
    human("STOP 5, the decision on codes below alpha 0.67", [("low_alpha_decisions.csv", "human/06_low_alpha/decisions.csv")])
    run("council.py", "consensus")
    run("council.py", "heldout-score")
    run("council.py", "cost")
    run("council.py", "report")
    run("council.py", "status")
    print("\ndemo: done. Open in a browser:\n  results dashboard   %s\n  review dashboard    %s\n  report              %s"
          % (ws / "dashboard.html", ws / "human" / "02_author_review" / "codebook_review.html", ws / "RESULTS.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
