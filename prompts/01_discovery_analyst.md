# 01 Discovery analyst (Stage 1; Lite and Full)

## Purpose

Three analysts from three model families read the whole corpus independently, once per research
question, and propose candidate codes with cited evidence. Separate readings broaden the
candidate space; reading once per question stops the most salient question from crowding out the
others. Each reading makes three ordered passes (semantic, latent, contrastive) so that the report
can say what the later passes found that a face-value reading would not. Every proposal must be
reviewable: a code carries its definition, include and exclude rules, every supporting unit, and
verbatim anchor quotes that a program checks against the corpus.

## Who receives it, and what it sees

- Each of the three analysts (roles A, B, C; one family each), once per research question, and
  once per block when the corpus is split into blocks.
- Sees: this brief and the corpus file (or one block of it). Never sees another analyst's output.

## Inputs

| Placeholder | Filled with |
|---|---|
| `{{ANALYST}}` | analyst id (A, B or C) |
| `{{RQ_BLOCK}}` | the research question for this reading, its rationale, and the list of the other questions |
| `{{CORPUS_FILE}}`, `{{N_UNITS}}` | the corpus (or block) file and the number of units in it |
| `{{UNITS}}`, `{{UNIT}}`, `{{RESPONDENT}}`, `{{RESPONDENTS}}` | study vocabulary from config (`study.unit_name`, ...) |
| `{{CORPUS_DESCRIPTION}}` | `study.corpus_description` |
| `{{EXAMPLE_UID}}`, `{{ID_PREFIX}}`, `{{RQ_ID}}` | an example unit id, the code id prefix (`<analyst>-<rq slug>`), the question id |
| `{{OUTPUT_PATH}}` | where the file goes, e.g. `discovery/v0/per_rq/analyst_A_RQ1.json` |
| `{{MAX_LABEL_WORDS}}`, `{{MIN_SUPPORT}}` | thresholds (14 words; 3 units) |
| `CONTEXT` (condition) | true when the corpus has a `context` column |

## Output schema

One JSON object, written to `{{OUTPUT_PATH}}`, exactly as in the prompt below. The program
(`council.py validate`) checks: `n_read` equals the number of units supplied; every cited id
exists; every quote is an exact, in-sequence substring of its cited unit's text (a match only
after normalizing whitespace, case or punctuation is reported but not accepted); quoted units are
in `participants`; no duplicate ids; at least `min(3, n_participants)` quotes from distinct
units; `layer` is one of `semantic`, `latent`, `contrastive`; every unit is either cited by a code
or listed in `uncodeable`.

<!-- BEGIN PROMPT -->
# Discovery: analyst {{ANALYST}} (layered reading)

You are one of three analysts reading this corpus independently. You cannot see the other
two and must not guess what they will say; divergence is what reconciliation measures.

## Research question for this reading

{{RQ_BLOCK}}

## The three layers, in sequence

Read the WHOLE corpus three times, in this order, and keep the readings apart. Every code
you return carries a `layer` field saying which reading produced it.

1. **semantic**: What people say, at face value. Group answers describing the same concrete thing. A {{RESPONDENT}} would recognise the code as a description of what they said.
2. **latent**: The arrangement under the answer; what has to be true for the answer to make sense. Two answers with different wording may describe one arrangement, and vice versa.
3. **contrastive**: Conditions and boundaries; where responses split; who gates what; prefer codes that separate people over codes everyone would accept.

Do the semantic pass first and write its codes down before starting the latent pass; do the
latent pass before the contrastive pass. A later layer may reuse units already coded in an
earlier layer; it must not restate an earlier code under a new label. If a later reading finds
nothing an earlier one did not, say so in `notes` rather than inventing codes. Two-unit codes
are reported honestly with `n_participants: 2`.

## The corpus

`{{CORPUS_FILE}}`: {{N_UNITS}} {{UNITS}}. {{CORPUS_DESCRIPTION}}
Each unit starts with its id in brackets (`[{{EXAMPLE_UID}}]`) on its own line. Read the whole file.
<!-- IF CONTEXT -->
Some units are followed by a line starting `CONTEXT:`. It holds the same {{RESPONDENT}}'s answer to a
complementary question. Read it only to understand an underspecified unit. Never code it, never
cite a unit for something only its CONTEXT says, and never quote from it.
<!-- ENDIF CONTEXT -->

## What you produce

One JSON object written to `{{OUTPUT_PATH}}`:

```json
{
  "analyst": "{{ANALYST}}",
  "lens": "layered",
  "n_read": {{N_UNITS}},
  "codes": [
    {
      "id": "{{ID_PREFIX}}-01",
      "layer": "semantic", "rq": "{{RQ_ID}}",
      "label": "at most {{MAX_LABEL_WORDS}} words, in the {{RESPONDENTS}}' terms",
      "definition": "what this covers, one or two sentences",
      "include": "what counts",
      "exclude": "what looks similar and goes elsewhere, naming the neighbouring code id",
      "participants": ["{{EXAMPLE_UID}}"],
      "anchor_quotes": [{"uid": "{{EXAMPLE_UID}}", "quote": "verbatim, trimmed to the relevant clause"}],
      "n_participants": 1,
      "candidate_theme": "T1"
    }
  ],
  "candidate_themes": [{"theme_id": "T1", "label": "optional grouping", "codes": ["{{ID_PREFIX}}-01"]}],
  "uncodeable": [],
  "notes": "what each layer added; anything the reconciler should know"
}
```

## Rules

- **Read every unit before proposing anything.** Set `n_read` to the number of units you
  actually read; it is checked against the corpus size.
- **Every code carries its unit ids.** A code without units behind it is not a code.
- **Label**: verb-led or noun-phrase, no method jargon, at most {{MAX_LABEL_WORDS}} words, in the
  {{RESPONDENTS}}' terms; a {{RESPONDENT}} who wrote the {{UNIT}} would recognise it as a description of what they said.
  Do not restate the research question as a code.
- **Definition** in the {{RESPONDENTS}}' terms; **include** (what counts); **exclude** (what looks
  similar and goes elsewhere, naming the neighbouring code by id).
- **Anchor quotes**: at least 3, from at least 3 different units, each **verbatim** from the
  unit's text: copy the characters exactly (same case, punctuation and spacing), trim to a clause,
  never paraphrase or stitch fragments (use `...` only to elide within one unit, in order). A
  machine checks every quote for an exact match.
- Every quote's unit id must be in that code's `participants` list. No duplicates. Never pad.
- **A unit may take several codes, or none.** Two units is still a code: report it honestly
  with `n_participants: 2`; the {{MIN_SUPPORT}}-unit floor is applied at reconciliation, not by you.
- **`uncodeable` lists the units with nothing bearing on {{RQ_ID}}.** Every unit is either cited by a code or listed there.
- Keep meaningfully different or opposing positions in separate codes.
- Optional `candidate_themes` grouping codes; every referenced code id must exist.
- **Ids**: `{{ID_PREFIX}}-01`, `{{ID_PREFIX}}-02`, ...  Unit ids are exactly as printed, e.g. `{{EXAMPLE_UID}}`.
- **`layer`** is one of `semantic`, `latent`, `contrastive` and is required on every code.
- Return one JSON object and nothing else. Write it to the file named above; do not write
  or read any other file in `discovery/`.

## What this is for

The three code sets are reconciled on shared units (not on wording), reviewed by researchers,
then applied by three coders. Your codes are instrument readings: cite evidence for each. The
`layer` field lets the report say what the later readings found that the first did not.
<!-- END PROMPT -->

## Follow-up instructions (sent by the program with the same brief)

The provenance check (`council.py validate`) returns failures to the analyst at most
`max_repairs` times (default 2), and returns unaccounted units once. The program sends the brief
again, with the analyst's own file, the corpus, and one of these instructions.

<!-- BEGIN INSTRUCTION completeness -->
Your file accounts for {{N_ACCOUNTED}} of the {{N_UNITS}} units. The brief requires every unit to be read and either cited by a code or listed in `uncodeable`. The units below are neither. Read each one; add it to the participants of an existing code it fits (with an anchor quote if the code needs one), propose new codes where the units share something no code covers, or list it in `uncodeable`. Keep every existing code unless a unit shows it is wrong. Return the complete revised file under the key `{{OUTPUT_PATH}}`.

{{UNIT_IDS}}
<!-- END INSTRUCTION completeness -->

<!-- BEGIN INSTRUCTION repair -->
Your discovery file failed the provenance check with the errors below. Fix every error (copy quotes character for character from the cited unit; cite only units that exist; quote only units in the code's participants; remove duplicate ids) and return the complete corrected file under the key `{{OUTPUT_PATH}}`.

{{ERRORS}}
<!-- END INSTRUCTION repair -->
