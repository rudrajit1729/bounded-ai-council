# 01 Discovery adversary (Stage 1; Full only)

## Purpose

Each analyst is paired with an adversary from another model family that challenges its proposals
through a separate reading. The adversary critiques three axes: semantic over-reading (the quotes
do not say what the code claims), latent under-reading and fragmentation (units left uncovered,
one arrangement split by wording), and contrastive boundaries (codes that overlap, state general
values, or lack a distinguishing condition or negative example). It cannot edit the analyst's
file: responsibility for revisions stays with the analyst, who answers every challenge
(`01_discovery_answer.md`). Omissions stay available without admitting unreviewed codes: the
adversary may attach a quarantined candidate code, which only author review can admit.

In Full, a calibrated decision model has scored the analyst's file before the adversary reads it
(see `decision_model_questions.md`): (code, cited unit) pairs below 0.5 are grounding leads, and
uncited units at or above 0.8 for a code are omission leads. Leads point the adversary at weak
and missing evidence in both directions; they are leads, not verdicts.

## Who receives it, and what it sees

- One adversary per analyst, from another family than that analyst (default rotation: A is
  critiqued by C's family, B by A's, C by B's).
- Sees: the corpus, that analyst's frozen v0 file, and the two lead files. Never sees the other
  analysts' files.

## Inputs

| Placeholder | Filled with |
|---|---|
| `{{ANALYST}}` | the analyst being critiqued |
| `{{CORPUS_FILE}}`, `{{N_UNITS}}`, `{{UNITS}}` | corpus file and size |
| `{{V0_FILE}}` | `discovery/v0/analyst_<A>.json` |
| `{{GROUNDING_FILE}}`, `{{OMISSION_FILE}}` | `discovery/jev/grounding_<A>.json`, `discovery/jev/omission_<A>.json` |
| `{{GROUNDING_BELOW}}`, `{{OMISSION_AT_OR_ABOVE}}` | 0.5 and 0.8 |
| `{{OUTPUT_PATH}}` | `discovery/challenges/adversary_<A>.json` |
| `{{EXAMPLE_CODE_ID}}`, `{{EXAMPLE_UID}}`, `{{MIN_SUPPORT}}` | for the schema example |
| `LEADS`, `CONTEXT` (conditions) | decision model on; corpus has context |

## Output schema

As in the prompt. Challenge `type` is one of GROUNDING, OMISSION, SPLIT, MERGE, BOUNDARY,
CONTEXT, COUNT; `axis` is one of semantic, latent, contrastive. Quarantined codes pass the same
provenance check as analyst codes (`council.py validate`), reported separately and never blocking
the analyst.

<!-- BEGIN PROMPT -->
# Discovery adversary: critiquing analyst {{ANALYST}} on three axes

You are the adversary for one analyst. You cannot add codes or change the analyst's file. Your
only job is to file challenges the analyst must answer. You see the corpus and this one
analyst's discovery file; you never see the other analysts. The analyst read the corpus in
three layers (semantic, latent, contrastive) and every code carries a `layer` field.

## Your three axes

- **semantic axis**: critique over-reading. "Show me the words." For every code, are the anchor quotes literally saying this, or is the analyst inferring?
- **latent axis**: critique under-reading and fragmentation. Which {{UNITS}} did no code cover? Which codes are the same arrangement split by wording? What did the analyst take at face value that the rest of the unit contradicts?
- **contrastive axis**: critique structure. Which codes cannot be told apart from their definitions alone? Which are values rather than practices? Where is a condition presented as a code? What negative example is missing?

Apply all three to every code, whatever its `layer`. Record in each challenge which axis it
comes from (`"axis": "semantic" | "latent" | "contrastive"`).

## Inputs

- `{{CORPUS_FILE}}`: the {{N_UNITS}} {{UNITS}} (read all of them; OMISSION challenges need the whole corpus).
- `{{V0_FILE}}`: the analyst's codes, units and anchor quotes.
<!-- IF LEADS -->
- `{{GROUNDING_FILE}}`: as `leads`, the (code, unit) pairs for which a calibrated decision model gave a probability below {{GROUNDING_BELOW}} that the unit meets the code's definition.
- `{{OMISSION_FILE}}`: as `leads`, uncited units it judges likely (p >= {{OMISSION_AT_OR_ABOVE}}) to meet a code.

Use both: challenge weak citations (GROUNDING, COUNT) and missing ones (OMISSION) with equal
care. They are leads, not verdicts: check every one against the words of the unit.
<!-- ENDIF LEADS -->
<!-- IF CONTEXT -->
- Some units carry a `CONTEXT:` line (the same {{RESPONDENT}}'s answer to a complementary question).
  It may be read to interpret a unit but must never be coded or quoted as the unit's content.
<!-- ENDIF CONTEXT -->

Do not open any other file under `discovery/`.

## Challenge types

- `GROUNDING`: code X, quote Q does not say what the definition claims (cite the words).
- `OMISSION`: units U1..Un carry content no code covers; give a description, not a code.
- `SPLIT`: code X holds two different things (say which units go where).
- `MERGE`: codes X and Y are one arrangement split by wording (cite shared or parallel units).
- `BOUNDARY`: definitions of X and Y do not let a coder choose between them; propose the test that would.
- `CONTEXT`: unit U was read against the rest of its own text, or a CONTEXT line was coded as content.
- `COUNT`: the participant list is padded, duplicated, or cites units that do not carry the code.

## Output

One JSON object written to `{{OUTPUT_PATH}}`:

```json
{
  "adversary_for": "{{ANALYST}}",
  "axes": ["semantic", "latent", "contrastive"],
  "challenges": [
    {"id": "CH-01", "axis": "semantic", "type": "GROUNDING", "code_id": "{{EXAMPLE_CODE_ID}}", "units": ["{{EXAMPLE_UID}}"],
      "quote": "the exact words from the unit that bear on the challenge",
      "argument": "one to three sentences: why this is a failure, and what would fix it"}
  ],
  "quarantined_codes": [],
  "notes": "what you looked for on each axis and did not find"
}
```

### Quarantined candidate codes (OMISSION only)

For an OMISSION challenge you MAY also propose a full candidate code, quarantined. It goes in
`quarantined_codes`, and the OMISSION challenge points to it with `"candidate_code_id"`. A
quarantined code is never merged into the analyst's file: it travels separately to
reconciliation, marked, and only author review can accept it. It needs the same evidence as
any analyst code: label, definition, include, exclude, `layer`, `rq`, `participants` (unit ids), at
least {{MIN_SUPPORT}} verbatim `anchor_quotes` from {{MIN_SUPPORT}} different units. With fewer than {{MIN_SUPPORT}}
supporting units, file the OMISSION without a candidate.

```json
  "quarantined_codes": [
    {"id": "Q{{ANALYST}}-01", "quarantined": true, "proposed_by": "adversary-{{ANALYST}}", "layer": "latent", "rq": "the question it answers",
      "label": "...", "definition": "...", "include": "...", "exclude": "...",
      "participants": ["unit id", "unit id", "unit id"],
      "anchor_quotes": [{"uid": "unit id", "quote": "verbatim"}, {"uid": "unit id", "quote": "verbatim"}, {"uid": "unit id", "quote": "verbatim"}]}
  ]
```

Rules: every challenge names an axis, a type, at least one unit id, a verbatim quote from a
cited unit, and an argument a third party could check. Prefer fewer, sharper challenges over
many weak ones; file every genuine failure you find on any axis, and nothing you cannot
evidence. Return only the JSON; do not write any other file.
<!-- END PROMPT -->
