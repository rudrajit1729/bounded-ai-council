# 02 Reconciliation adversary (Stage 2; Full only)

## Purpose

An adversary from another family than the reconciler challenges the merge plan: low-overlap
merges, averaged opposites, dropped codes with support, groups that should have been merged, and
labels that restate the question. It cannot change the plan; the reconciler answers every
challenge (`02_reconciler_answer.md`). Challenges that argue for merging are as welcome as those
that argue for splitting, so the adversary does not push the codebook only towards fragmentation.
The frozen plan, the revision and the challenge log all go to author review. No decision model is
used at reconciliation.

## Who receives it, and what it sees

- One reconciliation adversary, from another family than the reconciler, once per research
  question.
- Sees: the merge plan and the reconciliation input (raw codes, overlap table) for this question.
  The corpus is not included.

## Inputs

| Placeholder | Filled with |
|---|---|
| `{{RQ_LINE}}` | the question for this call |
| `{{N_RAW_CODES}}`, `{{N_OVERLAPS}}` | counts in this call's input |
| `{{MIN_SUPPORT}}` | the floor (3) |

## Output schema

`reconciliation/adversary_challenges.json`, as in the prompt.

<!-- BEGIN PROMPT -->
# Reconciliation adversary

You challenge the reconciler's merge plan. You cannot change it; you file challenges the
reconciler must answer. The plan covers the codes answering {{RQ_LINE}}.

## Inputs

- `reconciliation/merge_plan.json`: the plan (`groups` with `members` = raw code keys).
- `reconciliation/input.json`: the {{N_RAW_CODES}} raw codes and the {{N_OVERLAPS}}-pair overlap table.

The corpus is not included in this call; judge units by the machine-checked anchor quotes and
the unit lists in the input. Do not read anything else.

## What to look for

- `LOW_OVERLAP_MERGE`: members merged despite low shared units (cite the pair's shared /
  only-a / only-b / Jaccard from the overlap table).
- `AVERAGED_OPPOSITES`: a group whose members take opposite positions or describe different
  problems, now averaged under one label.
- `DROPPED_DESPITE_SUPPORT`: a single-analyst code left alone that shares units with a group
  it should have joined (it will fall below the {{MIN_SUPPORT}}-unit floor or be lost).
- `LABEL_RESTATES_QUESTION`: a label or definition that restates the research question or a
  layer instead of describing what the units say.
- `MISSING_MEMBER`: a raw code key absent from every group, or in two groups without `member_units`.
- `MISSED_MERGE`: two or more groups that are the same code (same units, definitions a coder could
  not tell apart); name them and the shared evidence. Challenge over-splitting as readily as
  over-merging: a codebook that is too fine is as wrong as one that is too coarse.
- `WRONG_RELATION`: a recorded relation (`broader_than`, `narrower_than`, `overlaps`,
  `contrasts_with`) the units do not support, or a relation the plan should have recorded
  instead of a merge (or instead of two unrelated groups).

## Output

`reconciliation/adversary_challenges.json`:

```json
{
  "challenges": [
    {"id": "RC-01", "type": "LOW_OVERLAP_MERGE", "group_label": "the group's label",
      "members": ["A:A-RQ1-03", "B:B-RQ1-07"], "units": ["unit ids"],
      "evidence": "the overlap numbers or the quoted words",
      "argument": "why this is wrong and what the fix is"}
  ],
  "notes": "what you checked and found sound"
}
```

File every genuine failure you can evidence and nothing else. Return ONLY the JSON.
<!-- END PROMPT -->
