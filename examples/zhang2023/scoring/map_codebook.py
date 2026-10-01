#!/usr/bin/env python3
# Copied from the paper's experiment (demo_v2/ground_truth/map_codebook.py) as a worked example. Only the
# path set-up changed: set ZHANG_DEMO_ROOT to the experiment folder. Outputs are written there, as in
# the experiment; copy the folder first if you want to keep the original results untouched.
"""
Map a council codebook onto Zhang et al.'s categories, from the two codebooks alone.

The mapper sees the council's codes (label, definition, include, exclude) and Zhang et al.'s
category definitions (zhang_codebook_v2.json). It never sees their labels on any thread or any
council assignment. An author audits every cell afterwards (human/04_mapping_audit).

  python3 map_codebook.py <codebook.json> <out.json>

Standard library; model calls through ../models.py (GPT-5.6-Terra, reasoning effort low).
"""
from __future__ import annotations
import json, sys
from pathlib import Path

import os
# The experiment's folder (demo_v2 of the paper's project): set ZHANG_DEMO_ROOT to it. Data and model
# drivers are read from there; nothing is hard-coded to one machine.
ROOT = Path(os.environ["ZHANG_DEMO_ROOT"]).resolve()
HERE = ROOT / "ground_truth"
sys.path.insert(0, str(HERE.parent))
import models  # noqa: E402

BRIEF = """# Mapping two codebooks

Two research teams coded the same Stack Overflow threads about GitHub Copilot, independently and
with different codebooks. You will map each code of team 1 (`council_codebook.json`) onto the
categories of team 2 (`zhang_categories.json`), using the definitions alone. You do not see any
coded thread.

For each team-1 code, list every team-2 category that a thread carrying the team-1 code would
also carry, under team 2's definition, in at least a typical case. Give the relation for each:
`equivalent` (same scope), `narrower` (the team-1 code is a sub-case of the category), `broader`
(the category is a sub-case of the team-1 code) or `overlaps` (partly the same). A team-1 code may
map to several categories or to none; say `none` rather than forcing a match. Judge by the
definitions, include and exclude clauses, not by similar words.

Return one JSON object under the key `mapping.json`:

{"mapping": [{"code_id": "T01", "categories": [{"id": "LC01", "relation": "narrower",
  "reason": "one sentence"}]}, {"code_id": "T02", "categories": []}]}

Every team-1 code must appear exactly once.
"""


RQ_DIM = {"RQ1.4": "Functions", "RQ1.5": "Purposes", "RQ2.1": "Benefits",
          "RQ2.2": "Limitations & challenges", "RQ2.3": "Expected features"}


NAME2ID = {}


def normalise(d) -> list:
    """Accept {"mapping": [{code_id, categories}]} or {"mapping": {code_id: [categories]}}, and
    category items keyed id / category_id / category (id or name)."""
    m = d.get("mapping", d) if isinstance(d, dict) else d
    if isinstance(m, dict):
        m = [{"code_id": k, "categories": v if isinstance(v, list) else v.get("categories", [])} for k, v in m.items()]
    out = []
    for x in m:
        cats = []
        for c in x.get("categories") or []:
            if isinstance(c, str):
                c = {"id": c}
            cid = c.get("id") or c.get("category_id") or c.get("category") or c.get("zhang_id") or ""
            cid = NAME2ID.get(str(cid).strip().lower(), cid)
            if cid:
                cats.append({"id": cid, "relation": c.get("relation", ""), "reason": c.get("reason", "")})
        out.append({"code_id": x.get("code_id") or x.get("id"), "categories": cats})
    return out


def main():
    """One mapping call per research question: the council's codes for that question against
    Zhang et al.'s categories for the same question (both schemes code per question)."""
    book = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2]).resolve()
    zc = json.loads((HERE / "zhang_codebook_v2.json").read_text())["categories"]
    NAME2ID.update({c["name"].strip().lower(): c["id"] for c in zc})
    models.WHOLE_CORPUS_STAGES.add("mapping")
    models.DEFAULT_REASONING_STAGES.add("mapping")   # the mapping is the measuring instrument: reasoning on
    models.GPT_EFFORT_BY_STAGE["mapping"] = "medium"
    mapping = []
    for rq, dim in RQ_DIM.items():
        work = out.parent / "_mapping_inputs" / out.stem / rq
        work.mkdir(parents=True, exist_ok=True)
        codes = [{k: c.get(k, "") for k in ("id", "label", "definition", "include", "exclude")}
                 for c in book["codes"] if c.get("rq") == rq]
        if not codes:
            continue
        cats = [{k: c[k] for k in ("id", "dimension", "name", "definition")} for c in zc
                if c["dimension"].lower().startswith(dim.lower()[:8])]
        (work / "council_codebook.json").write_text(json.dumps({"research_question": rq, "codes": codes}, indent=1))
        (work / "zhang_categories.json").write_text(json.dumps({"categories": cats}, indent=1))
        (work / "brief.md").write_text(BRIEF)
        part = work / "mapping.json"
        if not part.exists():
          models.call(stage="mapping", role="mapper", family="GPT", brief=work / "brief.md", batch=rq,
                    inputs=[("council_codebook.json", work / "council_codebook.json"),
                            ("zhang_categories.json", work / "zhang_categories.json")],
                    outputs=[("mapping.json", str(part.relative_to(HERE.parent)))], root=HERE.parent,
                    instruction=(f"Both teams coded {rq}. Map the {len(codes)} team-1 codes onto the "
                                 f"{len(cats)} team-2 categories for the same question. A category's definition "
                                 "lists everything it covers; map a code to every category whose definition "
                                 "covers what a thread carrying the code describes. Go through every category for "
                                 "every code and decide each pair; a code often belongs to two or three categories "
                                 "(for example, a keyboard-shortcut conflict is both a difficulty of integration and a "
                                 "lack of customization when the definitions say so). Return every code."))
        got = normalise(json.loads(part.read_text()))
        missing = [c for c in codes if c["id"] not in {x["code_id"] for x in got}]
        if missing:
            extra = work / "mapping_missing.json"
            if not extra.exists():
                (work / "council_missing.json").write_text(json.dumps({"research_question": rq, "codes": missing}, indent=1))
                models.call(stage="mapping", role="mapper", family="GPT", brief=work / "brief.md", batch=rq + "-missing",
                            inputs=[("council_codebook.json", work / "council_missing.json"),
                                    ("zhang_categories.json", work / "zhang_categories.json")],
                            outputs=[("mapping.json", str(extra.relative_to(HERE.parent)))], root=HERE.parent,
                            instruction=f"Map every one of these {len(missing)} codes; return each code_id exactly once.")
            got += normalise(json.loads(extra.read_text()))
        mapping += got
    out.write_text(json.dumps({"protocol": "one call per research question, categories of the same dimension",
                               "mapping": mapping}, indent=1))
    ids = {c["id"] for c in book["codes"]}
    got = {x["code_id"] for x in mapping}
    print(f"mapped {len(got & ids)} of {len(ids)} codes; missing {sorted(ids - got)}; "
          f"{sum(len(x['categories']) for x in mapping)} cells")


if __name__ == "__main__":
    main()
