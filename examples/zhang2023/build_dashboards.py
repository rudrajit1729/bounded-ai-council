#!/usr/bin/env python3
"""
Render the paper's coding results on the 256 Stack Overflow threads as two results dashboards, with
no model and no key:

    python3 examples/zhang2023/build_dashboards.py      # writes dashboard_lite.html and dashboard_full.html here

Inputs (all in this folder): data/threads.csv and data/splits.json (the threads and the paper's split),
results/approved_codebook_v1.2.json (the 72 approved codes), and each coder's assignments in
results/L/coder_long.csv (Lite coding) and results/LJA/coder_long.csv (Full, after the coding adversaries).

The script recomputes consensus and reliability with this repository's own Stage 5 code
(pipeline/reliability.py) on the 192 evaluation threads, checks every code's alpha against the paper's
files (results/L_eval/reliability.csv, results/LJA_eval/reliability.csv), stops if any differs, and
writes the dashboards with pipeline/dashboard.py. As in the paper, the authors dropped the codes below
alpha 0.67 rather than revise the codebook, and the dashboards record that decision.

Standard library only.
"""
from __future__ import annotations

import csv
import html
import json
import shutil
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "pipeline"))
import config as C  # noqa: E402
import council as K  # noqa: E402
import dashboard as DB  # noqa: E402
import reliability as R  # noqa: E402

CODERS = OrderedDict([("1", "Claude Opus 5"), ("2", "GPT-5.6"), ("3", "Gemini Flash 3.7")])
PAPER = {"L": {"name": "Lite", "cost": 35.26, "per100": 13.77}, "LJA": {"name": "Full", "cost": 86.60, "per100": 33.83}}


def read_csv(p):
    csv.field_size_limit(10 ** 9)
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def coder_rows(cond):
    return [OrderedDict([("coder", r["coder"]), ("uid", r["uid"]), ("batch", "-"), ("codes", [c for c in r["codes"].split("|") if c]),
                         ("why", r["why"]), ("uncovered_note", r["uncovered_note"])]) for r in read_csv(HERE / "results" / cond / "coder_long.csv")]


def build(mode: str, out: Path):
    data = C.read_config_file(HERE / "config.yaml")
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "paper-run"
        data["mode"], data["workspace"] = mode, str(ws)
        data["study"]["corpus_csv"] = str(HERE / "data" / "threads.csv")
        cfg = C.Config(data, HERE / "config.yaml")
        K.cfg, K.W = cfg, ws
        (ws / "data").mkdir(parents=True)
        shutil.copyfile(HERE / "data" / "threads.csv", ws / "data" / "corpus.csv")
        shutil.copyfile(HERE / "data" / "splits.json", ws / "data" / "splits.json")
        (ws / "codebooks").mkdir()
        book = json.loads((HERE / "results" / "approved_codebook_v1.2.json").read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
        (ws / "codebooks" / "approved_codebook.json").write_text(json.dumps(book), encoding="utf-8")
        corpus = OrderedDict((r["uid"], r) for r in read_csv(ws / "data" / "corpus.csv"))
        evaluation = json.loads((ws / "data" / "splits.json").read_text())["evaluation"]
        prim = "LJA" if mode == "full" else "L"
        summaries = OrderedDict()
        for cond in (["L", "LJA"] if mode == "full" else ["L"]):
            rows = coder_rows(cond)
            dec = OrderedDict()
            if cond == prim:
                # first pass to find the codes below the floor; the paper's authors dropped them
                res = R.run(rows=[OrderedDict(r) for r in rows], coders=list(CODERS), problems=[], corpus=corpus, book=book, cfg=cfg,
                            rel_units=evaluation, out=ws / "scratch", label=cond)
                for c in res["summary"]["codes_dropped_alpha_below_floor"]:
                    dec[c] = OrderedDict([("decision", "drop"), ("reason", "the paper's authors dropped the codes below 0.67 rather than revise the codebook"),
                                          ("decided_by", "the paper's authors")])
                d = ws / "human" / "06_low_alpha"
                d.mkdir(parents=True, exist_ok=True)
                with open(d / "decisions.csv", "w", newline="", encoding="utf-8") as fh:
                    w = csv.writer(fh)
                    w.writerow(["code", "decision", "reason", "decided_by"])
                    for c, x in dec.items():
                        w.writerow([c, x["decision"], x["reason"], x["decided_by"]])
            res = R.run(rows=rows, coders=list(CODERS), problems=[], corpus=corpus, book=book, cfg=cfg, rel_units=evaluation,
                        out=ws / "results" / cond, label=cond, low_alpha_decisions=dec)
            # the paper's figures, recomputed: every code's alpha must match results/<cond>_eval/reliability.csv
            paper = {r["code"]: r for r in read_csv(HERE / "results" / ("%s_eval" % cond) / "reliability.csv")}
            mine = {r["code"]: r for r in res["rel"]}
            bad = [c for c in paper if c in mine and paper[c]["alpha"] and abs(float(paper[c]["alpha"]) - mine[c]["alpha"]) > 1e-9]
            ps = json.loads((HERE / "results" / ("%s_eval" % cond) / "summary.json").read_text())
            if bad or abs(ps["alpha_median"] - res["summary"]["alpha_median"]) > 1e-9:
                raise SystemExit("%s: recomputed alpha differs from the paper's files for %s" % (cond, bad or "the median"))
            summaries[cond] = res["summary"]
        DB.bind(K)
        s = summaries[prim]
        n_codes = book.get("n_approved") or len(book["codes"])
        DB.OPTIONS = OrderedDict([
            ("title", "The paper's run: %s on 256 Stack Overflow threads" % PAPER[prim]["name"]),
            ("subtitle_html", "Corpus: the Stack Overflow threads about GitHub Copilot that Zhang et al. (2023) analysed, rebuilt as of 18 June 2023 "
                              "(<a href=\"data/ATTRIBUTION.md\">attribution, CC BY-SA</a>). Reliability is computed on the 192 evaluation threads."),
            ("links", [("README.md", "About this example"), ("results/approved_codebook_v1.2.json", "The approved codebook (JSON)"),
                       ("results/%s_eval/reliability.csv" % prim, "Every code's agreement (CSV)"),
                       ("dashboard_%s.html" % ("lite" if mode == "full" else "full"), "The %s dashboard" % ("Lite" if mode == "full" else "Full"))]),
            ("about_html", about_html(mode, n_codes, s)),
            ("human_html", "<ul><li>Held-out sample: two authors independently applied the approved codebook to a held-out random sample of 50 "
                           "evaluation threads without seeing model assignments and resolved their differences; agreement with the Full "
                           "council's consensus over the %d approved codes was a pooled Cohen's kappa of <b>0.787</b> (paper, Section 5).</li>"
                           "<li>Spot-check: two authors checked coder rationales against the codebook on a random 10%% of the coded threads.</li>"
                           "<li>Codes below 0.67 went to the authors, who dropped them rather than revise the codebook.</li>"
                           "<li>The researchers' own files (blind pass, review, held-out labels) are not part of this folder.</li></ul>" % n_codes),
            ("cost_html", "<p>From the paper's call log, at 2026 list prices: Lite cost <b>$%.2f</b> for the 256 threads (about $%.0f per 100), "
                          "Full <b>$%.2f</b> (about $%.0f per 100). The call log itself is not part of this folder. "
                          "<a href=\"../../SETUP.md\">SETUP.md</a> explains how cost scales with your corpus.</p>" % (
                              PAPER["L"]["cost"], PAPER["L"]["per100"], PAPER["LJA"]["cost"], PAPER["LJA"]["per100"])),
            ("footer_html", "Built by <code>examples/zhang2023/build_dashboards.py</code> from the paper's result files in this folder, with this "
                            "repository's own consensus and reliability code; every code's alpha matches the paper's files."),
        ])
        try:
            out.write_text(DB.build(), encoding="utf-8")
        finally:
            DB.OPTIONS = {}
        print("%s: %s, median alpha %.2f (min %.2f, max %.2f) on %d evaluation threads; %d of %d codes below 0.67; cross-family kappa median %.2f"
              % (out.name, PAPER[prim]["name"], s["alpha_median"], s["alpha_min"], s["alpha_max"], s["n_reliability_units"],
                 len(s["codes_dropped_alpha_below_floor"]), s["n_codes"], s["cross_family_kappa_median"]))
        return summaries


def about_html(mode, n_codes, s):
    e = html.escape
    roles = ", ".join("coder %s %s" % (k, e(v)) for k, v in CODERS.items())
    if mode == "lite":
        what = ("<b>Lite coding</b> (condition L): three coders, %s, each applied the approved codebook to every thread with every code shown; "
                "a code is assigned when at least two of the three coders assign it." % roles)
    else:
        what = ("<b>Full coding</b> (condition LJA): the same three coders (%s) coded every thread with the codes the decision model "
                "(TypeSafe Jev) screened for it; then an adversary from another family challenged each coder's batch and the coder "
                "answered, keeping or revising each assignment. Agreement after the adversaries is agreement among coder-adversary "
                "pipelines. The Lite row of the table below is the same codebook coded without screening or adversaries." % roles)
    return ("<p>%s</p><p>The codebook (version 1.2, <b>%d codes</b> across five research questions) came out of discovery by three "
            "analysts from the same three families, reconciliation by Claude Opus 5 with a GPT adversary, author review, and one "
            "consolidation round in which codes the coders could not apply consistently were merged, relabelled or dropped. "
            "The research questions are Zhang et al.'s own: functions implemented with Copilot, purposes of using it, benefits, "
            "limitations and challenges, and expected features.</p>"
            "<p>The paper reports a median alpha of 0.77 for Lite and 0.87 for Full on the evaluation threads; this page recomputes "
            "them from the coders' assignments: <b>%.2f</b> here.</p>" % (what, n_codes, s["alpha_median"]))


def main():
    build("lite", HERE / "dashboard_lite.html")
    build("full", HERE / "dashboard_full.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
