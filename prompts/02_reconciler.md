# 02 Reconciler (Stage 2; Lite and Full)

## Purpose

Three families have already surfaced the candidate space independently, so one reconciler
consolidates it. It decides which raw codes are the same code, gives each group one label and one
definition, and records how groups relate (equivalent, broader_than, narrower_than, overlaps,
contrasts_with). It merges on shared units together with definitions and quotes, never on similar
wording. Every raw code is assigned to a group, single-analyst codes may stand, and opposite
positions stay in separate groups linked by `contrasts_with`. It groups only codes that answer
the same research question, so reconciliation runs once per research question. It does not apply
the three-unit floor: a program does that afterwards (`council.py reconcile-apply`) and lists what
was dropped. It does not accept quarantined candidates; it only says how each relates to a group.

## Who receives it, and what it sees

- One reconciler (any family), once per research question.
- Sees: the validated raw codes for this question (with units, definitions, include/exclude,
  machine-checked anchor quotes, layer), the program-computed overlap table for cross-analyst
  pairs, and the quarantined candidates for this question. The corpus is not included.

## Inputs

| Placeholder | Filled with |
|---|---|
| `{{RQ_LINE}}` | the question id and text for this call |
| `{{N_UNITS}}`, `{{UNITS}}` | corpus size and unit name |
| `{{N_RAW_CODES}}`, `{{N_OVERLAPS}}`, `{{N_QUARANTINED}}` | counts in this call's input |
| `{{GROUPS_MIN}}`, `{{GROUPS_MAX}}` | the consolidation guide (`reconciliation.groups_per_rq`, default 5 to 15) |
| `{{MIN_SUPPORT}}`, `{{MAX_LABEL_WORDS}}`, `{{RESPONDENTS}}` | thresholds and vocabulary |

Input file (built by `council.py reconcile-prepare`): `reconciliation/input.json` for this
question, with `codes`, `overlap` and `quarantined_codes`.

## Output schema

`reconciliation/merge_plan.json` as in the prompt. The program checks every raw key is placed
(orphans become their own groups and are reported as errors), keeps many-to-many provenance,
normalizes relation-type synonyms, applies the floor, and writes the candidate codebook.

<!-- BEGIN PROMPT -->
# Reconciliation: reconciler brief

Three analysts read the same {{N_UNITS}} {{UNITS}} independently, each through three layers
(semantic, latent, contrastive). Decide which of their codes are the SAME code (equivalent), give
each group one label and one definition, and record how the groups relate to each other.

This call reconciles only the {{N_RAW_CODES}} raw codes that answer {{RQ_LINE}}. Every group gets
this question's `rq`.

## Input

`reconciliation/input.json`

- `codes`: {{N_RAW_CODES}} raw codes keyed `<analyst>:<id>`, each with its units, definition,
  include/exclude, verbatim anchor quotes (already machine-checked against the corpus) and the
  `layer` of the reading that produced it (semantic, latent, contrastive). Layer is provenance,
  not a grouping rule: codes from different layers that name the same units and the same thing
  are one code.
- `overlap`: {{N_OVERLAPS}} cross-analyst pairs that share at least one unit, with `shared`,
  `only_a`, `only_b`, `jaccard` and `containment` (shared / smaller set). This is
  **descriptive evidence**, not a rule: use it together with the definitions, the
  include/exclude clauses and the anchor quotes. Two codes worded differently that name the
  same units and whose definitions describe the same thing are one code; two worded alike that
  name different units are not. High containment with low Jaccard usually means one code is
  narrower than the other: record that as a relation rather than forcing a merge.
- `quarantined_codes`: {{N_QUARANTINED}} candidate codes proposed by discovery adversaries
  (OMISSION challenges), marked `quarantined`. **Do not place them in groups.** For each, say
  in `quarantined_assessment` which group it would be equivalent to or how it relates, so
  author review can decide; only author review may accept a quarantined code.

The corpus is not included in this call; judge units by the machine-checked anchor quotes and
the unit lists in the input.

## Output

`reconciliation/merge_plan.json`:

```json
{
  "groups": [
    {"group_id": "G01", "rq": "the question id",
      "label": "at most {{MAX_LABEL_WORDS}} words, in the {{RESPONDENTS}}' terms",
      "definition": "what it covers, one or two sentences",
      "include": "what counts",
      "exclude": "what looks similar and goes elsewhere, naming the other group's label",
      "members": ["A:A-RQ1-03", "B:B-RQ1-07", "C:C-RQ1-02"],
      "member_units": {"C:C-RQ1-02": ["unit ids of this member that belong here"]},
      "rationale": "one sentence: the evidence (units, definitions, quotes) for this grouping"}
  ],
  "relations": [
    {"type": "broader_than", "from": "G01", "to": "G04", "note": "G04 is a sub-case of G01"},
    {"type": "contrasts_with", "from": "G02", "to": "G07", "note": "the opposite position"}
  ],
  "quarantined_assessment": [
    {"key": "Q:QA-01", "relation": "equivalent", "to": "G03", "note": "..."}
  ],
  "notes": "what you could not resolve"
}
```

Relation types: `equivalent` (that is what a group is), `broader_than`, `narrower_than`,
`overlaps`, `contrasts_with`. Relations are between groups (`group_id`).

## Rules

- **Every raw code key appears in at least one group**, normally exactly one. A raw code that
  genuinely holds two things may be a member of two groups; then give `member_units` for it in
  each group (which of its units belong there). Provenance is kept many-to-many. Orphans are
  errors. A code you think worthless still gets its own group; the {{MIN_SUPPORT}}-unit floor is
  applied afterwards, mechanically.
- **Each raw code carries `rq`, the research question its reading answered. Group only codes
  with the same `rq`, and give every group its `rq`.**
- **Merge on evidence, not on similar wording**: shared units, matching definitions and
  include/exclude, quotes saying the same thing.
- **A single-analyst code may stand alone.** `n_analysts` is the strength signal, kept as provenance.
- **Aim for a codebook coders can apply: about {{GROUPS_MIN}} to {{GROUPS_MAX}} groups per research question.**
  Merge a narrower code into the broader group that covers it unless coders would need the
  distinction to answer the question; when you merge, record the narrower code in `relations` as
  `narrower_than` the group, so nothing is lost.
- **Preserve genuine disagreement.** Opposite positions are two groups joined by `contrasts_with`.
- **Do not invent codes.** Group only what the analysts proposed; a label must describe the
  members' units, not the research question.
- **No method jargon** in labels or definitions.

Return ONLY the JSON object.
<!-- END PROMPT -->
