# AGENTS.md: operating the council pipeline

Instructions for a coding agent (Claude Code, Codex, or any agent that can run shell commands) asked
to run the bounded AI council on a user's corpus. Follow them in order. Where this file says STOP,
stop and hand over to the user; do not continue past a human step on your own.

**If the user only wants to see how it works**, run the offline demo: `python3 pipeline/demo.py`. It
replays a recorded Full run on an invented 30-answer corpus (`examples/tiny/`), with dummy researcher
files, and needs no key and no network. Then point the user to
`examples/tiny/workspace/dashboard.html`, `examples/tiny/workspace/RESULTS.md` and
`examples/tiny/workspace/human/02_author_review/codebook_review.html`. A user without a terminal can
use the local app instead: `python3 pipeline/app.py`, then http://127.0.0.1:8765/.

## 0. Rules that hold throughout

1. **Programs decide what is deterministic.** Provenance checks, the support floor, consensus,
   reliability and the drop rule are computed by `pipeline/council.py`. Never compute or "fix" them by
   judgment, and never edit a model's output to make a check pass; send it back to the model (the
   scripts do this) or report the failure.
2. **Isolation.** Analysts never see each other's output; coders never see each other's output; an
   adversary sees only the role it critiques. Each model call is a fresh, stateless session with
   exactly the files its prompt lists. If you answer prompts through sub-agents, start a new one per
   prompt.
3. **Families.** Three analysts and three coders come from three model families. An adversary comes
   from another family than the role it critiques. Do not answer a role yourself unless you are that
   role's family, and then only in a fresh context. (The recorded demo in `examples/tiny/` breaks this
   rule on purpose: one agent role-played every family to make a demo, and its config says so. Never
   do that for a study.)
4. **Frozen files stay frozen.** `discovery/v0/` and the v0 coding (`coding/L`, `coding/LJ`) are
   read-only after `freeze`; revisions go to v1. Never overwrite `codebooks/approved_codebook.json`
   once coding has started; codebook versions are never mixed.
5. **Humans first, models second, where the method says so.** The blind pass is done before any
   researcher sees model output. Never show a researcher a discovery file, codebook, challenge log
   or dashboard before they have returned their blind pass. Never show model assignments to the
   researchers doing held-out coding.
6. **Secrets.** Keys stay in environment variables. Never print, read, copy or write a key (do not
   open shell profiles to look for one). The config holds only the variable's name.
7. **Data governance.** Before the first model call, confirm with the user that the corpus is
   de-identified and that consent terms allow every vendor in the config, and record this under
   `data_governance`.
8. **Never invent.** No codes, quotes, units, labels or numbers that the artifacts do not contain.
   Never write a human-derived number (blind pass, review, held-out agreement, spot-check) before the
   researchers have produced it.

## 1. Ask the user for these inputs

Do not start until you have all of them. Put them in `config.yaml` (copy `config.example.yaml`).

| Input | Config key | Notes |
|---|---|---|
| Mode | `mode` | `lite` or `full` (Full = adversaries + decision model). |
| Corpus | `study.corpus_csv` | CSV with `uid,text`; optional `context` (same respondent's answer to a complementary question; read, never coded), `question`, `block`, `stratum` (used to stratify samples), `link`. De-identified. |
| Research questions | `study.research_questions` | `id`, `text`, optional `rationale` (what the question means), optional `slug`. |
| Corpus description and vocabulary | `study.corpus_description`, `unit_name(_plural)`, `respondent_name(_plural)`, `scope_rule`, `topic_phrase` | One or two sentences the analysts read; the extraction rule all roles apply. |
| Issue codes | `issue_codes` | Defaults: wrong field, back-reference, non-response. Add study-specific ones if needed. |
| Model families available | `roles`, `models` | Which three families, through which CLI or API, with which model ids; the env var NAME of each API key. If only two families are available, say so and record the vendor caveat. |
| Decision model (Full) | `decision_model` | Jev (env var name of the key), a `command` with the same contract, `manual` (each request is written to `<workspace>/manual/` for you or the user to answer; not calibrated), or `enabled: false`. |
| Researchers | (your notes) | At least two people for the blind pass, author review, held-out coding and spot-check. |
| Data governance | `data_governance` | What leaves the machine, to which vendors, under which terms. |
| Prices (optional) | `prices` | USD per million input and output tokens per model id, dated. |

Then run, and fix every ERROR it prints (missing corpus, placeholder model ids, a family without a
`models` entry, an adversary from the same family, an unknown backend):

```bash
python3 pipeline/council.py --config config.yaml status
```
`status` also prints the next command to run; `status --json` gives the same for programs.

## 2. Choose how model calls are made

- **Route A, scripted (recommended).** Set each family's `backend` to `claude_cli`, `codex_cli`,
  `anthropic_api`, `openai_api`, `gemini_api` or `command`. `pipeline/run.py` makes every call, logs
  it, and runs the checks.
- **Route B, manual or agent-answered.** Set a family's `backend: manual` (and `answered_by:` the
  model that will answer). `run.py` writes each prompt it needs to
  `<workspace>/manual/<stage>__<role>__<batch>.prompt.md` and exits with status 3. For each prompt:
  send the whole file, in a fresh session, to a model of the right family (for example
  `claude -p < X.prompt.md > X.reply.json`, `codex exec - < X.prompt.md`, or a new sub-agent of that
  family); save the model's reply, unedited, as `<same name>.reply.json` next to the prompt; then
  rerun the same `run.py` command. Repeat until it finishes. The reply must be one JSON object keyed by
  the output paths the prompt names (for a `.jsonl` output, the value is a list of objects).
  What to expect:
  - Every prompt that can be written at once is written at once (all readings, all batches); prompts
    that depend on a reply (an adversary needs the coder's file; an answer needs the challenges)
    appear only after you rerun. A Full run of `examples/tiny/` took fifteen rounds of this.
  - Repair and completeness rounds get numbered names (`...__a1`, `...__a2`); each is a new prompt.
    Its `=== INSTRUCTION ===` section says what to fix; the reply is the complete corrected file
    (discovery v0) or a delta (discovery v1), as the instruction says.
  - With `decision_model.backend: manual`, each decision-model request is a prompt too
    (`jev-leads__analyst-<A>__<uid>`, `jev-screen__coders__<uid>`): one unit and a set of codes; the
    reply is `{"<code id>": probability, ...}`. These are many (one per unit per analyst, and one per
    unit at coding) and their probabilities are not calibrated; say so in the report.
  - To keep a manual run so that it can be replayed with no model access (for an audit or a demo):
    `python3 pipeline/council.py --config config.yaml export-replies --to replay`, then point a copy
    of the config at it with `backend: replay` and `replay_dir: replay` (models and decision model).
- **Route C, no scripts for model calls.** Possible but discouraged: section 6 lists, per role, the
  prompt file, its inputs and its output; you must still run every deterministic command listed there.

## 3. Stage by stage

`CFG` below stands for `--config config.yaml`. After every step, run `council.py CFG status`.

### Preparation

```bash
python3 pipeline/council.py CFG prepare
```
Check: the printout gives units, development/evaluation sizes, blind-pass and held-out sizes, blocks.
Set `discovery_block_size` (and rerun with `--force` before any model call) if the corpus does not fit
the analysts' context windows; never truncate.

```bash
python3 pipeline/human.py CFG blind-pass
```
**STOP 1 (can run in parallel with Stage 1).** Tell the user: hand `human/01_blind_pass/` to at least
two researchers now, before anyone sees model output. You may continue with the model stages, but do
not show any output to those researchers until they have returned their blind pass.

### Stage 1: discovery

```bash
python3 pipeline/run.py CFG discovery
```
What it does: one reading per analyst x research question (x block) with `prompts/01_discovery_analyst.md`;
the provenance check on each reading (cited ids exist; quotes are exact, in-sequence substrings of the
cited unit's text; quoted units are in the support list; no duplicates; enough quotes; `n_read` equals
the units supplied); up to `max_repairs` repair calls and one completeness round per reading; merge per
analyst into `discovery/v0/analyst_<A>.json`; validate; freeze.
Checks:
- `discovery/validation/v0_analyst_<A>.json` has `"status": "PASS"` for A, B, C.
- `discovery/validation/repairs.json`: note repairs and units unaccounted before and after the
  completeness round per reading (they are reported).
- If a reading FAILs after the repairs, stop and report the errors to the user. Nothing with an error
  goes to reconciliation.

**Full only:**
```bash
python3 pipeline/run.py CFG discovery-adversary
```
What it does: decision-model grounding and omission leads on each v0 file (`discovery/jev/`); one
adversary per analyst from another family (`prompts/01_discovery_adversary.md`); the analyst answers
(`prompts/01_discovery_answer.md`) with a delta that the program applies to v0 to make v1; the v1 file
passes the same check (repairs as deltas); quarantined candidate codes are checked and reported.
Checks: `discovery/validation/v1_analyst_<A>.json` PASS for all three; every challenge has an answer
(`discovery/answers/answer_<A>.json`).

### Stage 2: reconciliation

```bash
python3 pipeline/run.py CFG reconcile
```
What it does: builds the raw-code list and the cross-analyst overlap table (shared units, units held
alone, Jaccard, containment; same question only); one reconciler call per research question
(`prompts/02_reconciler.md`); in Full, the reconciliation adversary (`02_reconciliation_adversary.md`)
and the reconciler's answers (`02_reconciler_answer.md`), and also the Lite reconciliation on v0 for
comparison; then the program applies the three-unit floor, keeps many-to-many provenance, and writes
`codebooks/candidate_<lite|full>.json`.
Checks: the printout of `reconcile-apply`; `errors` in the candidate codebook (orphans are placed as
their own groups and reported; groups that mix questions are reported). Report them to the user.

### Stage 3: author review (researchers)

Only after the researchers have returned their blind pass:

```bash
python3 pipeline/human.py CFG review-dashboard
```
**STOP 2.** Tell the user: each of at least two researchers opens
`human/02_author_review/codebook_review.html`, reviews every code against every cited unit, gives
examples from development units only, and downloads their decisions (Finish tab). Then:

```bash
python3 pipeline/human.py CFG review-to-edits review_<A>.json review_<B>.json
```
(With no file names it reads every `.json` in `human/02_author_review/returned/`, where the app puts
the reviewers' files.) This writes `codebooks/review_edits.draft.json` (edits both reviewers agree on) and
`human/02_author_review/review_comparison.md` (what to negotiate). The researchers meet, resolve every
item by negotiated agreement, and save the final edit log as `codebooks/review_edits.json`:

```json
{"reviewed_by": "R1, R2", "status_note": "...", "blind_pass_codes_missing": ["..."],
 "edits": [
  {"op": "relabel", "id": "T01", "label": "...", "definition": "...", "include": "...", "exclude": "...", "rq": "RQ2", "reason": "..."},
  {"op": "merge", "into": "T01", "from": ["T03"], "reason": "..."},
  {"op": "split", "id": "T05", "into": [{"id": "T05a", "label": "...", "definition": "...", "include": "...", "exclude": "...", "units": ["U1", "U2", "U3"]}, {"id": "T05b", "...": "..."}], "reason": "..."},
  {"op": "move", "units": ["U012"], "from": "T02", "to": "T05", "reason": "..."},
  {"op": "drop", "id": "T04", "reason": "..."},
  {"op": "add", "id": "T90", "rq": "RQ1", "label": "...", "definition": "...", "include": "...", "exclude": "...", "units": ["U1", "U2", "U3"], "reason": "..."},
  {"op": "examples", "id": "T01", "positive": ["U001"], "negative": ["U009"]},
  {"op": "accept_quarantined", "key": "Q:QA-01", "id": "T91", "reason": "..."},
  {"op": "reject_quarantined", "key": "Q:QA-01", "reason": "..."},
  {"op": "relation", "type": "contrasts_with", "from": "T02", "to": "T07", "reason": "..."},
  {"op": "drop_relation", "from": "T02", "to": "T07", "type": "overlaps", "reason": "..."}]}
```

You may help the researchers turn their agreed decisions into this JSON; you may not decide for them.
Then:

```bash
python3 pipeline/council.py CFG approve        # writes codebooks/approved_codebook.json (version 1.0, closed)
```
Checks: the printout (codes approved, edits by type); warnings about fewer than two reviewers or codes
without positive examples go to the user. Examples outside the development units are ignored by the
program.

If review finds a gap that no candidate and its evidence can fill: copy `config.yaml` to a new file
with a new `workspace` and the reviewers' notes appended to `study.corpus_description`, run
`prepare`, `discovery` (and `discovery-adversary` in Full) and `reconcile` there, and bring the new
candidates to review as `add` edits (each with at least three cited units) before approving.

```bash
python3 pipeline/human.py CFG heldout-packet
```
**STOP 3 (can run in parallel with Stage 4).** Tell the user: at least two researchers code
`human/03_heldout_coding/` independently, without seeing any model assignment, resolve differences,
and save one `resolved.csv`.

### Stage 4: coding (and Stage 5 consensus)

```bash
python3 pipeline/run.py CFG code
```
What it does: batches of `batch_size` units; Lite coding with every code shown
(`prompts/04_coder.md`) into `coding/L`. Full adds decision-model screening (`coding/jev/screen.json`,
`coding/LJ/screening_plan.json`), screened coding into `coding/LJ`, freeze, then per coder and batch the
coding adversary with the decision model's disagreements as leads (`04_coding_adversary.md`) and the
coder's answer (`04_coder_answer.md`) into `coding/LJA`. Then consensus for every condition.
Checks: warnings about units missing from a coder's batch; `integrity` in
`results/<cond>/summary.json` (invalid codes used, units missing per coder, parse problems). Report
them; do not patch coder files.

### Stage 5: consensus, reliability and the drop rule

`run.py code` already ran it; to rerun (for example after the spot-check):

```bash
python3 pipeline/council.py CFG consensus
```
What it computes, per condition (`L`; Full: `LJ` = v0, `LJA` = v1):
- consensus: a code is assigned when at least 2 of 3 coders assign it; a unit two coders flag with an
  issue code is excluded from prevalence but kept in the file;
- per code, on the binary decision and on the evaluation units (`reliability.units`): Krippendorff's
  alpha, pairwise Cohen's kappa with 2x2 tables, raw, positive and negative agreement; the mean kappa
  over coder pairs from different families;
- the distribution: median, minimum, maximum, number below 0.67, number at or above 0.80 (no interval);
- **the low-alpha rule: every code with alpha below 0.67** is held out of prevalence and
  `consensus_retained.csv` and listed with its definition and agreement counts in
  `results/<cond>/reliability_report.md`, with the researchers' decision once they have made it
  (STOP 5 below); codes with undefined alpha (no variation) are listed beside them and not reported;
- survival (pairs proposed by at least one coder that at least two assign); uncovered and issue counts;
- Full: decision-model disagreements at consensus (assigned with p below 0.2) are held out of
  prevalence until the spot-check keeps them.
The results of the run are the primary condition: `L` in Lite, `LJA` in Full.

```bash
python3 pipeline/human.py CFG spot-check
```
**STOP 4.** Tell the user: at least two researchers check the rows of
`human/05_spot_check/spot_check.csv` against the codebook, fill `keep` and `note`, and save the
agreed file as `human/05_spot_check/decisions.csv`; report the sample size. Then rerun `consensus`.
(`keep = n` on an uncertain Full assignment keeps it out of prevalence; on any other row it is
recorded and counted in the report, and consensus is unchanged.)

```bash
python3 pipeline/human.py CFG low-alpha
```
**STOP 5.** If any code is below the floor, tell the user: the researchers read
`human/06_low_alpha/low_alpha_codes.md` (each code's definition and every unit the coders disagreed
on) and decide, per code, `drop` or `refine`, in `human/06_low_alpha/decisions.csv` (copy
`decisions_TEMPLATE.csv`; a refined code needs `new_definition`, and `new_label`, `new_include`,
`new_exclude` where they change). You may help them write the file; you may not decide for them. Then:
```bash
python3 pipeline/council.py CFG consensus      # records the decisions in the reports and the dashboard
python3 pipeline/council.py CFG refine         # only if a code is refined: archives this coding round
                                               # under archive/, writes codebook version 1.1 (dropped codes
                                               # removed); then rerun `run.py code` on the whole corpus
```
After a refine, the researchers also recode the held-out sample for the refined codes.

When the researchers' resolved held-out labels exist (as `human/03_heldout_coding/resolved.csv`, or
pass `--labels FILE`):
```bash
python3 pipeline/council.py CFG heldout-score
python3 pipeline/council.py CFG retention --human prior.csv     # only if the researchers coded the corpus first
```

### Report

```bash
python3 pipeline/council.py CFG cost
python3 pipeline/council.py CFG report        # writes <workspace>/RESULTS.md and <workspace>/dashboard.html
```
`dashboard.html` is the results dashboard (self-contained, no network): stage summary, reliability
with the codes below 0.67 and the researchers' decisions, prevalence, the codebook with example
quotes, and calls, tokens and cost by stage. `consensus` refreshes it too; `council.py dashboard`
rebuilds it alone.
When the researchers have written up their themes:
```bash
python3 pipeline/council.py CFG check-quotes writeup.md   # every "quote" [UID] must be an exact substring
```

## 4. What to report to the user

At the end (and briefly at every STOP), report from the artifacts, not from memory:

1. Mode, roster (family and model id per role, from `logs/calls.jsonl`), vendor caveat, data governance.
2. Stage 1: codes per analyst by layer; repairs and units unaccounted before and after the
   completeness round; validation status. Full: challenges by type and axis, accept/reject/partial,
   quarantined candidates.
3. Stage 2: raw codes, groups, kept, dropped below the floor, relations, apply errors. Full:
   reconciliation challenges and answers; Lite versus Full candidate counts.
4. Stage 3: reviewers, edits by type, approved codes, quarantined admitted, blind-pass codes the
   council lacked.
5. Stage 4/5: alpha median, min, max, number below 0.67 (dropped, by id), number at or above 0.80,
   cross-family kappa, survival, issue and uncovered counts; Full: the same for v0 and v1, cells
   changed, screening recall against Lite.
6. Human checks: held-out human-council agreement, spot-check sample size, the researchers'
   decision on every code below 0.67, retention if applicable.
7. Cost per stage. Anything that failed or was skipped, and why.
Point the user to `dashboard.html`, `RESULTS.md`, `results/<cond>/reliability_report.md` (the
supplement table of every code and the dropped codes) and `CHECKLIST.md`.

## 5. When something goes wrong

- A discovery reading fails after repairs: report the errors (`discovery/validation/per_reading/`);
  options are a rerun of that reading (delete its output file and rerun `run.py discovery`) or a
  different model for that family. Record the deviation.
- A reply is not parseable JSON: the raw reply is in `logs/raw/`; rerun the command (the step is
  retried); if it keeps failing, report it.
- A coder skipped units: consensus counts them as missing (reported); rerun only that batch by
  deleting its file before `freeze`, never after.
- Exit status 3: manual prompts are waiting (section 2, route B).
- `replay: no recorded reply ...`: a replayed run asked for a call the recording does not have (the
  config, corpus or a human file differs from the recorded run). `replay: the prompt ... differs`
  is a warning: the recorded reply is used for a prompt that changed.
- `status` tells you the next step at any point.

## 6. Running without the scripts for model calls (route C)

For each role: render the prompt (fill the placeholders from the table at the top of its file, from
`config.yaml` and the workspace), send it with exactly the listed input files (each under a line
`=== FILE: <path> ===`), save the reply's JSON to the output path, log the call with
`council.py CFG log-call --stage ... --role ... --family ... --model ... --inputs ... --outputs ...`, and run
the deterministic command shown.

| Role | Prompt | Inputs | Output | Then run |
|---|---|---|---|---|
| Analyst, one reading | `01_discovery_analyst.md` (briefs already rendered by `council.py CFG discovery-briefs` into `briefs/discovery/`) | `data/corpus.txt` or `data/blocks/<B>.txt` | `discovery/v0/per_reading/analyst_<A>_<RQ>.json` | after all readings: `council.py CFG merge-readings`, `validate --stage v0` (fix failures by sending the `repair` / `completeness` instruction from the same prompt file), `freeze --what discovery` |
| Decision model, leads (Full) | `decision_model_questions.md` | one unit + every v0 code of one analyst | `discovery/jev/grounding_<A>.json` (`leads`: cited pairs p < 0.5), `omission_<A>.json` (`leads`: uncited pairs p >= 0.8) | |
| Discovery adversary (Full) | `01_discovery_adversary.md` | corpus, `discovery/v0/analyst_<A>.json`, the two lead files | `discovery/challenges/adversary_<A>.json` | |
| Analyst's answer (Full) | `01_discovery_answer.md` | corpus, v0 file, challenges | `discovery/answers/answer_<A>.json`, `discovery/v1_delta/analyst_<A>.json` | `council.py CFG apply-delta --analyst <A>`, then `validate --stage v1` |
| Reconciler | `02_reconciler.md` (rendered by `council.py CFG reconcile-prepare --cond <lite or full>` into `briefs/reconciliation/`) | `reconciliation/<cond>/per_rq/<RQ>/input.json` (sent as `reconciliation/input.json`) | `reconciliation/<cond>/per_rq/<RQ>/merge_plan.json` | |
| Reconciliation adversary (Full) | `02_reconciliation_adversary.md` | input, plan | `.../adversary_challenges.json` | |
| Reconciler's answer (Full) | `02_reconciler_answer.md` | input, plan, challenges | `.../reconciler_answers.json`, `.../merge_plan_revised.json` | `council.py CFG reconcile-apply --cond <cond>` |
| Coder | `04_coder.md` (rendered by `council.py CFG code-prepare` into `briefs/coding/`) | `coding/batches/batch<n>.txt` | `coding/L/coder<k>_batch<n>.jsonl` | after all batches: `freeze --what coding`, `consensus` |
| Decision model, screening (Full) | `decision_model_questions.md` | one unit + every approved code | `coding/jev/screen.json` (`scores`: uid -> code -> p) | screened batches and per-batch briefs are built by `run.py code`; by hand, list per unit the codes with p >= 0.10, at least the top 5, plus a seeded 5% audit of the rest |
| Coding adversary (Full) | `04_coding_adversary.md` | batch, the coder's v0 file, leads (assigned p < 0.2; unassigned p >= 0.8) | `coding/LJA/challenges/coder<k>_batch<n>.json` | |
| Coder's answer (Full) | `04_coder_answer.md` | batch, v0 file, challenges | `coding/LJA/answers/coder<k>_batch<n>.json`, `coding/LJA/coder<k>_batch<n>.jsonl` | `consensus` |

Output schemas are in each prompt file, inside the prompt text the model receives.
