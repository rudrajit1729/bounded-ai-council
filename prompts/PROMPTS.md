# Prompt index

Every model role reads one prompt file. The text a model receives is the part of the file between
`<!-- BEGIN PROMPT -->` and `<!-- END PROMPT -->`, with every `{{PLACEHOLDER}}` filled and every
`<!-- IF NAME -->` block kept only when NAME applies. `pipeline/council.py` and `pipeline/run.py`
render them from `config.yaml`; when you run without scripts, fill them by hand from the tables at the
top of each file. Rendered briefs are kept in `<workspace>/briefs/`, so a report can publish exactly
what each model received.

The input files a role may see are sent with the brief, each under a line `=== FILE: <path> ===`,
and the model returns one JSON object keyed by the output paths the brief names (see `SYSTEM` in
`pipeline/models.py`). A role never sees files outside its list: analysts never see each other,
coders never see each other, adversaries see only the role they critique.

## Mode x stage x role

| Stage | Role | Lite | Full | Prompt file | Called | Output (in the workspace) |
|---|---|---|---|---|---|---|
| 1 Discovery | Analyst A, B, C | yes | yes | `01_discovery_analyst.md` | per analyst x research question (x block) | `discovery/v0/per_reading/analyst_<A>_<RQ>.json`, merged to `discovery/v0/analyst_<A>.json` |
| 1 Discovery | Analyst, provenance repair and completeness round | yes | yes | `01_discovery_analyst.md` (instructions `repair`, `completeness`) | when the check fails (at most 2 repairs, 1 completeness round) | same file, replaced |
| 1 Discovery | Decision model: grounding and omission | | yes | `decision_model_questions.md` | per unit x every v0 code of one analyst | `discovery/jev/grounding_<A>.json`, `omission_<A>.json` |
| 1 Discovery | Discovery adversary (other family) | | yes | `01_discovery_adversary.md` | per analyst (x block) | `discovery/challenges/adversary_<A>.json` |
| 1 Discovery | Analyst's answer | | yes | `01_discovery_answer.md` (+ instructions `repair`, `completeness` for v1) | per analyst (x block) | `discovery/answers/answer_<A>.json`, `discovery/v1_delta/analyst_<A>.json` -> `discovery/v1/analyst_<A>.json` |
| 2 Reconciliation | Reconciler | yes | yes | `02_reconciler.md` | per research question | `reconciliation/<cond>/per_rq/<RQ>/merge_plan.json` |
| 2 Reconciliation | Reconciliation adversary (other family) | | yes | `02_reconciliation_adversary.md` | per research question | `.../adversary_challenges.json` |
| 2 Reconciliation | Reconciler's answer | | yes | `02_reconciler_answer.md` | per research question | `.../reconciler_answers.json`, `.../merge_plan_revised.json` |
| 3 Author review | Researchers (no prompt) | yes | yes | `pipeline/human.py review-dashboard` | once | `codebooks/review_edits.json` -> `approved_codebook.json` |
| 4 Coding | Coder 1, 2, 3 (every code shown) | yes | yes (Lite baseline) | `04_coder.md` | per coder x batch | `coding/L/coder<k>_batch<n>.jsonl` |
| 4 Coding | Decision model: screening | | yes | `decision_model_questions.md` | per unit x every approved code | `coding/jev/screen.json` |
| 4 Coding | Coder, screened (`SCREENING` block on) | | yes | `04_coder.md` | per coder x batch | `coding/LJ/coder<k>_batch<n>.jsonl` (v0) |
| 4 Coding | Coding adversary (other family; decision-model leads) | | yes | `04_coding_adversary.md` | per coder x batch | `coding/LJA/challenges/coder<k>_batch<n>.json` |
| 4 Coding | Coder's answer | | yes | `04_coder_answer.md` | per coder x batch | `coding/LJA/answers/...`, `coding/LJA/coder<k>_batch<n>.jsonl` (v1) |
| 5 Reliability | Program (no prompt) | yes | yes | `pipeline/council.py consensus` | per condition | `results/<cond>/` |

`<cond>` is `lite` or `full` at reconciliation; at coding, the conditions are `L` (Lite), `LJ`
(screened, v0) and `LJA` (after adversaries, v1). In Full with the decision model switched off,
the adversaries critique `L` and write `LA`.

## Vendor rule

Three analysts and three coders come from three model families. Each adversary comes from another
family than the role it critiques (default rotation: A by C's family, B by A's, C by B's; the same for
coders 1, 2, 3). The reconciler may be any family; its adversary is another family.

## Reasoning settings

Discovery (with its repairs and answers) and reconciliation (with its answers) run at each model's
default reasoning; every other generative call runs with reasoning reduced
(`reasoning.default_stages`, `reasoning.reduced_effort`).

## Origin

These prompts generalize the briefs the paper's experiment actually sent
(`demo_v2/runs/full/briefs/`): study-specific text (Stack Overflow, GitHub Copilot, Zhang et al.'s
questions) became placeholders, and the briefs were brought into line with the method as written
where the two differed (exact quotes, both kinds of decision-model lead at once, the removal rule,
the contrastive axis name, CONTEXT handling). `examples/zhang2023/config.yaml` fills the
placeholders back with the experiment's values.
