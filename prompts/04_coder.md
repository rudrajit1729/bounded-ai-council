# 04 Coder (Stage 4; Lite and Full)

## Purpose

The approved, closed codebook must be applied throughout the corpus. Three coders from three
families independently code every unit, in batches of 20 to 50 (default 25). A coder writes a
rationale identifying the relevant text before assigning codes, which makes post-hoc
justification harder and each assignment inspectable. A unit takes zero or more codes. Coders
cannot introduce codes, so the codebook cannot drift: content no code fits is recorded as
`UNCOVERED` with a note and reported as a finding about the codebook. Data problems receive issue
codes rather than being dropped, so no single coder can remove a unit.

In Full, a calibrated decision model has scored every (unit, code) pair first, and each unit is
shown with the codes to consider for it: every code at or above the threshold (default 0.10),
never fewer than the top 5, plus a seeded audit share (default 5%) of screened-out codes. The
batch's codebook then contains only codes listed somewhere in the batch. Lite coding (every code
shown) is kept as the baseline against which screening recall is measured.

## Who receives it, and what it sees

- Each of three coders (1, 2, 3; one family each), once per batch.
- Sees: the closed codebook (or, when screening, the codes listed in this batch) and one batch.
  Never sees another coder's output.

## Inputs

| Placeholder | Filled with |
|---|---|
| `{{CODER}}` | coder id |
| `{{N_BATCHES}}`, `{{BATCH_SIZE}}`, `{{N_UNITS}}`, `{{UNITS}}`, `{{UNIT}}` | batching and vocabulary |
| `{{RQ_BLOCK_ALL}}` | every research question with its rationale |
| `{{SCOPE_RULE}}` | `study.scope_rule` |
| `{{ISSUE_BLOCK}}`, `{{ISSUE_IDS}}` | the issue codes and their definitions (config `issue_codes`) |
| `{{VALID_CODES}}`, `{{CODEBOOK_VERSION}}`, `{{CODEBOOK}}` | the approved codebook, rendered by `council.py` |
| `{{OUTPUT_PATH}}`, `{{EXAMPLE_UID}}`, `{{EXAMPLE_CODE}}` | output file pattern and schema example |
| `SCREENING`, `CONTEXT` (conditions) | Full screening; corpus has context |

## Output schema

JSONL, one object per unit, in batch order: `{"uid", "why", "codes", "uncovered_note"?}`. Codes
outside the approved set are dropped and reported by `council.py consensus` (integrity section).

<!-- BEGIN PROMPT -->
# Systematic coding: coder {{CODER}}

You are one of three coders applying an APPROVED, CLOSED codebook to every unit. This is the
deductive stage; the inductive work is finished. You never see the other coders' output.

## The one rule that matters most

**Do not invent codes.** Apply only the codes listed below, plus the `ISSUE_*` codes. If a unit
says something real that no code covers, assign `UNCOVERED` and say in `uncovered_note` what
it is: that is a finding about the codebook, and it is counted. Adding a code here would mean
early and late batches were coded against different schemes.

## What to code

`coding/batches/batch<N>.txt`: the batch named in your instruction ({{N_BATCHES}} batches of up to
{{BATCH_SIZE}} units, {{N_UNITS}} units in all). Each unit is one {{UNIT}}, headed by its id in brackets. Code **every** unit in the batch.
<!-- IF CONTEXT -->
Some units are followed by a `CONTEXT:` line: the same respondent's answer to a complementary
question. Read it only to understand an underspecified unit; never code it.
<!-- ENDIF CONTEXT -->

Research questions:

{{RQ_BLOCK_ALL}}

{{SCOPE_RULE}} A code may answer one question or several.
<!-- IF SCREENING -->

## Screening (this condition)

Under each unit in the batch, a line `Codes to consider for this unit:` lists the codes a
calibrated decision model judged possible for it. Consider only those codes for that unit
(plus the `ISSUE_*` codes and `UNCOVERED`). If the unit carries content that no listed code
fits, use `UNCOVERED` and say in `uncovered_note` what it is. The codebook below contains every
code listed anywhere in this batch.
<!-- ENDIF SCREENING -->

## How to code

For each unit, in this order:
1. Write `why`: one short phrase naming what in the text you are responding to.
2. Then assign `codes`.

Rationale before label is deliberate: it makes the reasoning checkable and stops a label being
chosen first and justified second.

- A unit may take **several codes**. Assign a code when the unit meets its definition and
  include clause and is not excluded; check the exclude clause before assigning a neighbour.
{{ISSUE_BLOCK}}
  Use these instead of leaving a unit uncoded; they are counted, not excluded silently. If
  codeable content and a data problem coexist, code the content and add the issue code only
  when its definition is met.
- `UNCOVERED`: real content, bearing on a research question, that no code covers; write
  `uncovered_note`.
- Judge only what the text says. Do not infer what a {{RESPONDENT}} probably meant.

## Output

One JSON object per line, one line per unit, in batch order, written to
`{{OUTPUT_PATH}}` (this file is frozen once written):

```json
{"uid": "{{EXAMPLE_UID}}", "why": "the words in the unit that the code rests on, in a short phrase", "codes": ["{{EXAMPLE_CODE}}"]}
{"uid": "{{EXAMPLE_UID}}", "why": "a concern no code in the book describes", "codes": ["UNCOVERED"], "uncovered_note": "what the content is"}
```

Valid code ids: {{VALID_CODES}}, plus {{ISSUE_IDS}}, UNCOVERED. Write only that file.

## The codebook (closed, version {{CODEBOOK_VERSION}})

{{CODEBOOK}}
<!-- END PROMPT -->
