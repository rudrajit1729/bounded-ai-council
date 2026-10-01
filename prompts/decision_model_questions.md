# Decision-model questions (Full only)

## Purpose

Verbalized confidence from a generative model is not a calibrated probability. In Full, a
calibrated yes/no model answers the yes/no questions of discovery and coding with probabilities,
so that generative reasoning is spent where it is needed: the adversaries get leads, and the
coders see a shorter list of codes per unit. The decision model never writes text, never changes
the codebook, and never votes: its probabilities are leads and filters, and every assignment
still rests on a coder's rationale. The specified implementation is TypeSafe's Jev; any model
with the same contract (one probability of "yes" per question, from fixed state) can take its
place. There is no decision model at reconciliation.

## Where it is used, and the thresholds (config `thresholds`)

| Use | When | Question asked for | Lead or filter |
|---|---|---|---|
| Grounding | Stage 1, after discovery v0 is frozen, before the adversary reads | every (code, cited unit) pair in an analyst's v0 file | p < `grounding_lead_below` (0.5): a lead for GROUNDING and COUNT challenges |
| Omission | Stage 1, same time | every (code, uncited unit) pair in an analyst's v0 file | p >= `omission_lead_at_or_above` (0.8): a lead for OMISSION challenges |
| Screening | Stage 4, after the codebook closes | every (unit, approved code) pair | a coder sees every code with p >= `screening_tau` (0.10), never fewer than the top `screening_top_k` (5), plus a seeded `screening_audit_share` (5%) of the screened-out codes |
| Coding leads | Stage 4, after screened coding | the screening scores against each coder's v0 assignments | assigned with p < `coding_lead_assigned_below` (0.2), or not assigned with p >= `coding_lead_unassigned_at_or_above` (0.8): leads for the coding adversary, and the uncertain assignments added to the researchers' spot-check |

Screening recall is measured against Lite coding of the same corpus (`council.py report`).

## The question

All four uses ask the same question, one per code, with the unit as state. In the experiment the
wording was: "Does this Stack Overflow thread contain something a poster says about GitHub Copilot
that meets the definition of `code`, as its include and exclude clauses describe?" The general
template is below; `{{UNIT}}`, `{{RESPONDENT}}` and `{{TOPIC}}` come from `study.unit_name`,
`study.respondent_name` and `study.topic_phrase` (empty, or a phrase such as " about GitHub Copilot"
with a leading space).

<!-- BEGIN QUESTION code_applies -->
Does this {{UNIT}} contain something a {{RESPONDENT}} says{{TOPIC}} that meets the definition of `code`, as its include and exclude clauses describe?
<!-- END QUESTION code_applies -->

### Request (one per unit)

```json
{
  "state": {"unit_text": "the unit's text", "context": "the paired CONTEXT, when the corpus has it"},
  "questions": {
    "<code id>": {
      "question": "the question above",
      "code": {"label": "...", "definition": "...", "include": "...", "exclude": "...",
               "research_question": "the code's research question (omitted when decision_model.include_research_question is false)"}
    }
  }
}
```

The state key for the unit text is `decision_model.state_key` (default `unit_text`; the
experiment used `thread`). CONTEXT is interpretive only: the unit text is what is judged.

### Response

```json
{"<code id>": 0.83, "<code id>": 0.02}
```

One probability of "yes" in [0, 1] per question, or null when the model cannot answer. No text.

## Implementations

- `decision_model.backend: typesafe` (default): POST to `decision_model.endpoint` with
  `{"state": ..., "model": decision_model.model, "questions": {id: {"type": "noul", "instructions": {...}}}}`;
  the key is read from the environment variable named in `decision_model.api_key_env`
  (default `TYPESAFE_API_KEY`). The answer for each id is `answers[id].noul`.
- `decision_model.backend: command`: any program. The pipeline writes the request above as JSON on
  the program's stdin and reads the response above as JSON from its stdout. Use this to swap in
  another calibrated yes/no model (a fine-tuned classifier, a logprob-calibrated model, a local
  service). Validate it before use: the thresholds above were fixed for Jev; recalibrate them on a
  calibration sample (never on evaluation units) when you change the model, the corpus or the
  codebook version, and report the per-code recall of screening.
- `decision_model.backend: manual`: each request is written, with the instructions above, to
  `<workspace>/manual/<stage>__<role>__<uid>.prompt.md`; the reply (the response above) is saved
  next to it as `.reply.json`. For an agent-driven run without a decision model; the probabilities
  are not calibrated, and the report must say so.
- `decision_model.backend: replay` with `replay_dir`: answers from replies recorded from a manual run
  (`council.py export-replies`); used by the offline demo.

Every request is logged in `logs/calls.jsonl` (stage `jev-leads` at discovery, `jev-screen` at
coding) with the sha256 of the request, never the key. Grounding and omission come from one request
per unit: the same scores are read against cited pairs (grounding) and uncited pairs (omission).
