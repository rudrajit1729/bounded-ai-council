# 04 Coding adversary (Stage 4; Full only)

## Purpose

Each coder is paired with an adversary from another family that challenges its assignments and
omissions for one batch: rationales that fail a definition, missed assignments, coded context,
and missed issues. The adversary sees the full codebook (not the screened subset), the batch, the
coder's assignments, and the decision model's disagreements with that coder as leads: codes
assigned with low probability (below 0.2) or not assigned with high probability (0.8 or above).
It cannot change assignments; the coder answers (`04_coder_answer.md`). The coder's original
output stays frozen as `v0` and the revision is `v1`; both are scored.

## Who receives it, and what it sees

- One coding adversary per coder, from another family than that coder, once per batch.
- Sees: the batch (every unit), the coder's frozen v0 assignments for it, the leads file, and the
  full codebook. Never sees another coder's file.

## Inputs

| Placeholder | Filled with |
|---|---|
| `{{CODER}}`, `{{UNIT}}` | coder id; unit name |
| `{{LEAD_ASSIGNED_BELOW}}`, `{{LEAD_UNASSIGNED_AT_OR_ABOVE}}` | 0.2 and 0.8 |
| `{{ISSUE_IDS}}`, `{{CODEBOOK_VERSION}}`, `{{CODEBOOK}}` | as in 04_coder.md |
| `{{EXAMPLE_UID}}`, `{{EXAMPLE_CODE}}` | schema example |
| `LEADS`, `CONTEXT` (conditions) | decision model on; corpus has context |

## Output schema

`coding/challenges/coder<k>_batch<N>.json`, as in the prompt.

<!-- BEGIN PROMPT -->
# Coding adversary: challenging coder {{CODER}}

You see one coder's assignments for one batch, the batch text and the closed codebook. You
cannot change assignments; you file challenges the coder must answer.

## Inputs

- `coding/batches/batch<N>.txt`: the batch named in your instruction.
- `coding/v0/coder{{CODER}}_batch<N>.jsonl`: coder {{CODER}}'s assignments for it.
<!-- IF LEADS -->
- `coding/leads/coder{{CODER}}_batch<N>.json`: the decision model's disagreements with this coder:
  codes assigned with probability below {{LEAD_ASSIGNED_BELOW}}, and codes not assigned with probability at or
  above {{LEAD_UNASSIGNED_AT_OR_ABOVE}}. Check these first; they are leads, not verdicts.
<!-- ENDIF LEADS -->
- The codebook below. Do not read any other coder's file.

## Challenge types

- `FALSE_POSITIVE`: the unit was given code X but does not meet its definition or falls under
  its exclude clause; cite the definition clause it fails.
- `FALSE_NEGATIVE`: the unit meets code X and was not given it; cite the words in the unit.
- `ISSUE_MISSED`: the unit should have been flagged with an issue code ({{ISSUE_IDS}}), or was
  flagged with one but has codeable content.
<!-- IF CONTEXT -->
- `CONTEXT_CODED`: an assignment rests on the unit's `CONTEXT:` line rather than on the unit's
  own words.
<!-- ENDIF CONTEXT -->

## Output

`coding/challenges/coder{{CODER}}_batch<N>.json`:

```json
{
  "coder": "{{CODER}}", "batch": 1,
  "challenges": [
    {"id": "CC-01", "type": "FALSE_NEGATIVE", "uid": "{{EXAMPLE_UID}}", "code_id": "{{EXAMPLE_CODE}}",
      "quote": "the exact words from the unit", "argument": "why the definition is met (or not)"}
  ],
  "notes": "what you checked and found sound"
}
```

Check every unit. File every genuine failure you can evidence against the codebook's words,
and nothing else. Return ONLY the JSON.

## The codebook (closed, version {{CODEBOOK_VERSION}})

{{CODEBOOK}}
<!-- END PROMPT -->
