#!/usr/bin/env python3
# Copied from the paper's experiment (demo_v2/ground_truth/map_debate.py) as a worked example. Only the
# path set-up changed: set ZHANG_DEMO_ROOT to the experiment folder. Outputs are written there, as in
# the experiment; copy the folder first if you want to keep the original results untouched.
"""
Mapping an approved codebook onto Zhang et al.'s categories with two models, a debate and a judge.

  1. Two mappers, independently, per research question: Claude Opus 5 and GPT-5.6-Sol. Each sees the
     council codes for one question and Zhang et al.'s categories for the same question, nothing else.
  2. Debate: every cell (code, category) on which they disagree goes back to both, with the other's
     reason; each keeps or withdraws its position, with a reason.
  3. Judge: cells still disputed go to GPT-5.6-Sol in a fresh call, which reads both arguments and
     decides. Agreed cells stand.
  4. The lead author checks the result (mapping_audit_<version>.csv).
No model sees any labelled thread or any council assignment.

  python3 map_debate.py <codebook.json> <out.json>
"""
from __future__ import annotations
import csv, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import os
# The experiment's folder (demo_v2 of the paper's project): set ZHANG_DEMO_ROOT to it. Data and model
# drivers are read from there; nothing is hard-coded to one machine.
ROOT = Path(os.environ["ZHANG_DEMO_ROOT"]).resolve()
HERE = ROOT / "ground_truth"
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import models  # noqa: E402
from map_codebook import BRIEF, RQ_DIM, normalise, NAME2ID  # noqa: E402

MAPPERS = {"claude": "claude-opus-5", "gpt": "gpt-5.6-sol"}
JUDGE = "gpt-5.6-sol"

DEBATE = """# Second round: disagreements with another mapper

Another mapper mapped the same codes onto the same categories independently. Below are the cells
(code, category) on which you disagree, with each side's reason. For each cell, decide whether a
thread carrying the code would typically also carry the category under team 2's definition. Keep
your position or change it, with one sentence.

Return one JSON object under the key `debate.json`:
{"cells": [{"code_id": "T03", "category_id": "LC02", "include": true, "reason": "one sentence"}]}
Every listed cell must appear exactly once."""

JUDGE_BRIEF = """# Deciding disputed mapping cells

Two mappers disagree on whether each council code below should map to a category of Zhang et al.'s
scheme. Read both codes' and categories' definitions and both arguments, and decide each cell: map it
when a thread carrying the code would typically also carry the category under the category's
definition. Judge only from the definitions.

Return one JSON object under the key `judge.json`:
{"cells": [{"code_id": "T03", "category_id": "LC02", "include": true, "reason": "one sentence"}]}"""


def cells(mapping):
    return {(m["code_id"], c["id"]): c.get("reason", "") for m in mapping for c in m["categories"]}


def main():
    book = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2]).resolve()
    work = out.parent / "_debate" / out.stem
    work.mkdir(parents=True, exist_ok=True)
    zc = json.loads((HERE / "zhang_codebook_v2.json").read_text())["categories"]
    NAME2ID.update({c["name"].strip().lower(): c["id"] for c in zc})
    zdef = {c["id"]: c for c in zc}
    models.DEFAULT_REASONING_STAGES.add("mapping")
    models.GPT_EFFORT_BY_STAGE["mapping"] = "medium"
    root = HERE.parent
    (work / "brief.md").write_text(BRIEF)
    (work / "debate.md").write_text(DEBATE)
    (work / "judge.md").write_text(JUDGE_BRIEF)
    final, log = [], []

    def one_rq(item):
        rq, dim = item
        codes = [{k: c.get(k, "") for k in ("id", "label", "definition", "include", "exclude")}
                 for c in book["codes"] if c.get("rq") == rq]
        if not codes:
            return rq, [], []
        cats = [{k: c[k] for k in ("id", "dimension", "name", "definition")} for c in zc
                if c["dimension"].lower().startswith(dim.lower()[:8])]
        d = work / rq
        d.mkdir(exist_ok=True)
        (d / "codes.json").write_text(json.dumps({"research_question": rq, "codes": codes}, indent=1))
        (d / "cats.json").write_text(json.dumps({"categories": cats}, indent=1))
        maps = {}
        for name, model in MAPPERS.items():
            f = d / f"map_{name}.json"
            if not f.exists():
                models.call(stage="mapping", role=f"mapper-{name}", family="GPT", model=model, brief=work / "brief.md",
                            batch=rq, inputs=[("council_codebook.json", d / "codes.json"), ("zhang_categories.json", d / "cats.json")],
                            outputs=[("mapping.json", str(f.relative_to(root)))], root=root,
                            instruction=(f"Both teams coded {rq}. Map every one of the {len(codes)} codes. A code often "
                                         "belongs to two or three categories; decide every (code, category) pair."))
            maps[name] = cells(normalise(json.loads(f.read_text())))
        a, b = maps["claude"], maps["gpt"]
        agreed = set(a) & set(b)
        disputed = sorted(set(a) ^ set(b))
        lines = []
        for (cid, cat) in disputed:
            side = "claude" if (cid, cat) in a else "gpt"
            lines.append({"code_id": cid, "category_id": cat,
                          "mapped_by": "mapper 1" if side == "claude" else "mapper 2",
                          "not_mapped_by": "mapper 2" if side == "claude" else "mapper 1",
                          "reason_for_mapping": (a.get((cid, cat)) or b.get((cid, cat)) or "")})
        decided = {}
        if disputed:
            (d / "disputed.json").write_text(json.dumps({"cells": lines}, indent=1))
            votes = {}
            for name, model in MAPPERS.items():
                f = d / f"debate_{name}.json"
                if not f.exists():
                    models.call(stage="mapping", role=f"mapper-{name}-debate", family="GPT", model=model,
                                brief=work / "debate.md", batch=rq,
                                inputs=[("council_codebook.json", d / "codes.json"), ("zhang_categories.json", d / "cats.json"),
                                        ("disputed.json", d / "disputed.json")],
                                outputs=[("debate.json", str(f.relative_to(root)))], root=root,
                                instruction=f"You are {'mapper 1' if name == 'claude' else 'mapper 2'}.")
                votes[name] = {(x["code_id"], x["category_id"]): (bool(x.get("include")), x.get("reason", ""))
                               for x in json.loads(f.read_text()).get("cells", [])}
            still = []
            for cell in disputed:
                va, vb = votes["claude"].get(cell), votes["gpt"].get(cell)
                if va and vb and va[0] == vb[0]:
                    decided[cell] = (va[0], "agreed after debate")
                else:
                    still.append({"code_id": cell[0], "category_id": cell[1],
                                  "mapper_1": {"include": va[0] if va else None, "reason": va[1] if va else ""},
                                  "mapper_2": {"include": vb[0] if vb else None, "reason": vb[1] if vb else ""}})
            if still:
                f = d / "judge.json"
                (d / "still.json").write_text(json.dumps({"cells": still}, indent=1))
                if not f.exists():
                    models.call(stage="mapping", role="judge", family="GPT", model=JUDGE, brief=work / "judge.md", batch=rq,
                                inputs=[("council_codebook.json", d / "codes.json"), ("zhang_categories.json", d / "cats.json"),
                                        ("disputed.json", d / "still.json")],
                                outputs=[("judge.json", str(f.relative_to(root)))], root=root)
                for x in json.loads(f.read_text()).get("cells", []):
                    decided[(x["code_id"], x["category_id"])] = (bool(x.get("include")), "judge: " + x.get("reason", ""))
        keep = set(agreed) | {c for c, (inc, _) in decided.items() if inc}
        rows = [{"code_id": c, "category_id": k, "status": "agreed" if (c, k) in agreed else decided.get((c, k), (None, ""))[1]}
                for c, k in sorted(set(a) | set(b) | set(decided))]
        mapping = [{"code_id": c["id"], "categories": [{"id": k} for (cc, k) in sorted(keep) if cc == c["id"]]} for c in codes]
        return rq, mapping, [dict(r, kept=(r["code_id"], r["category_id"]) in keep) for r in rows]

    with ThreadPoolExecutor(5) as ex:
        for rq, mapping, rows in ex.map(one_rq, RQ_DIM.items()):
            final += mapping
            log += [dict(r, rq=rq) for r in rows]
    out.write_text(json.dumps({"protocol": f"two mappers ({', '.join(MAPPERS.values())}), debate, judge {JUDGE}; author check",
                               "mapping": final}, indent=1))
    lab = {c["id"]: c for c in book["codes"]}
    with (out.parent / f"mapping_audit_{out.stem}.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["rq", "code_id", "code_label", "category_id", "category_name", "kept", "how decided", "AUTHOR: correct? (y/n)"])
        for r in log:
            w.writerow([r["rq"], r["code_id"], lab.get(r["code_id"], {}).get("label", ""), r["category_id"],
                        zdef.get(r["category_id"], {}).get("name", "?"), r["kept"], r["status"], ""])
    n_agree = sum(1 for r in log if r["status"] == "agreed")
    print(f"cells considered {len(log)}; agreed outright {n_agree}; kept {sum(r['kept'] for r in log)}; "
          f"codes with no category {sum(1 for m in final if not m['categories'])} of {len(final)}")


if __name__ == "__main__":
    main()
