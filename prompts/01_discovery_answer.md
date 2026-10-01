# 01 Discovery analyst's answer to its adversary (Stage 1; Full only)

## Purpose

Responsibility for revisions stays with the analyst. The analyst answers every challenge with
ACCEPT, REJECT (with a reason) or PARTIAL, and revises its own file. The original stays frozen as
`v0`; the revision is `v1`, so the comparison is preserved and the challenge log goes to
reconciliation and author review. Citations move in both directions under one rule: a citation is
removed only when the unit clearly fails the definition (naming the clause it fails), and added
when the unit meets it. A decision model's low score or an adversary's doubt is a lead, not a
reason. A quarantined candidate is never copied into the analyst's file; the analyst may give a
view on it or adopt the omission with its own code and evidence.

## Who receives it, and what it sees

- The original analyst (same family and model as its discovery reading).
- Sees: its frozen v0 file, the challenges filed against it, and the corpus. Never sees other
  analysts' work.

## Inputs

| Placeholder | Filled with |
|---|---|
| `{{ANALYST}}`, `{{CORPUS_FILE}}`, `{{N_UNITS}}` | as in 01_discovery_analyst.md |
| `{{V0_FILE}}`, `{{CHALLENGES_FILE}}` | `discovery/v0/analyst_<A>.json`, `discovery/challenges/adversary_<A>.json` |
| `{{ANSWERS_PATH}}`, `{{DELTA_PATH}}` | `discovery/answers/answer_<A>.json`, `discovery/v1_delta/analyst_<A>.json` |

## Output schema

Two outputs, returned as one JSON object keyed by path. The second is a delta: the program
(`council.py apply-delta`) applies it to v0 to produce `discovery/v1/analyst_<A>.json`, which then
passes the same provenance check as v0 (with up to two repair rounds and one completeness round).

<!-- BEGIN PROMPT -->
# Answering the adversary: analyst {{ANALYST}} (layered reading)

An adversary has read your discovery file and filed challenges on three axes (semantic, latent,
contrastive). Answer every challenge, then revise your discovery file. You are still analyst
{{ANALYST}}: same layered reading, same rules as your discovery brief, same corpus
(`{{CORPUS_FILE}}`, {{N_UNITS}} units).

## Inputs

- `{{V0_FILE}}`: your file (frozen; do not modify it).
- `{{CHALLENGES_FILE}}`: the challenges.
- `{{CORPUS_FILE}}`.

Do not open any other file under `discovery/`.

## The rule for citations

Remove a citation only when the unit clearly fails the code's definition or falls under its
exclude clause, and name the clause it fails in your answer. A decision model's low score, or the
adversary's doubt, is a lead, not a reason. Additions follow the same rule in the other
direction: cite a unit when it meets the definition.

## Outputs

1. `{{ANSWERS_PATH}}`: the challenge log:

```json
{
  "analyst": "{{ANALYST}}",
  "answers": [
    {"challenge_id": "CH-01", "answer": "ACCEPT", "reason": "one or two sentences",
      "revision": "what changed in the file (code ids, units), or 'none'"}
  ]
}
```

`answer` is `ACCEPT` (you revised as asked), `REJECT` (give the reason; the challenge is
wrong or unevidenced), or `PARTIAL` (you revised in part; say which part).

If the adversary attached a quarantined candidate code to an OMISSION challenge, answer the
challenge as usual and add `"quarantined_view": "ENDORSE" | "OPPOSE" | "NEUTRAL"` with a
reason. Do NOT copy the quarantined code into your revised file, even if you endorse it: it
travels separately and only author review can accept it. You may instead adopt the OMISSION with
your own code (your own units and quotes), marked `"adopted_from_adversary": true`.

2. `{{DELTA_PATH}}`: your revision as a delta against your v0 file. A program applies it to v0
   to produce your v1 file:

```json
{
  "replace": ["complete code objects, same schema as the discovery file, for every code you changed or added"],
  "remove": ["ids of codes you removed"],
  "uncodeable_add": ["unit ids"],
  "uncodeable_remove": ["unit ids"]
}
```

Codes you leave untouched are not repeated. Every code in `replace` needs its `rq`, `layer`,
`participants` and verbatim `anchor_quotes`, the same evidence as any other code. A code adopted
from an OMISSION challenge carries `"adopted_from_adversary": true`. If you reject every challenge,
every list is empty.

Rules: quotes verbatim (exact characters); quote ids in the participant list; no padding; two-unit
codes are reported honestly. Return only these two outputs.
<!-- END PROMPT -->

## Follow-up instructions (sent by the program with the same brief)

When the v1 file fails the provenance check, or leaves units neither cited nor listed as
uncodeable, the program sends the brief again with the corpus and the current v1 file, and one of
these instructions. The reply is again a delta, applied to the current v1.

<!-- BEGIN INSTRUCTION repair -->
Your revised file `{{V1_FILE}}` failed the provenance check with the errors below. Fix every error (copy quotes character for character from the cited unit; cite only units that exist; quote only units in the code's participants; remove duplicate ids). Return, under the key `{{DELTA_PATH}}`, a JSON object {"replace": [complete code objects for every code you changed or added], "remove": [ids of codes you removed], "uncodeable_add": [unit ids], "uncodeable_remove": [unit ids]}. Codes you leave untouched are not repeated.

{{ERRORS}}
<!-- END INSTRUCTION repair -->

<!-- BEGIN INSTRUCTION completeness -->
Your revised file `{{V1_FILE}}` accounts for {{N_ACCOUNTED}} of the {{N_UNITS}} units. Every unit must be either cited by a code or listed in `uncodeable`. The units below are neither. Read each one; add it to the participants of an existing code it fits (with an anchor quote if the code needs one), propose new codes where the units share something no code covers, or list it in `uncodeable`. Return, under the key `{{DELTA_PATH}}`, a JSON object {"replace": [complete code objects for every code you changed or added], "remove": [], "uncodeable_add": [unit ids], "uncodeable_remove": []}.

{{UNIT_IDS}}
<!-- END INSTRUCTION completeness -->
