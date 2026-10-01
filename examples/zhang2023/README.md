# The paper's data: 256 Stack Overflow threads about GitHub Copilot

The paper evaluates the procedure on a public corpus that humans had already coded: the Stack
Overflow posts about GitHub Copilot that Zhang et al. (2023) analysed by constant comparison
(*Demystifying Practices, Challenges and Expected Features of Using GitHub Copilot*, IJSEKE
33(11-12); their dataset: Zenodo doi:10.5281/zenodo.8123303). This folder holds the threads, the
paper's coding results, two results dashboards built from them, and the configs to run the
pipeline on the same threads yourself.

## What is here

| File | What it is |
|---|---|
| `dashboard_lite.html`, `dashboard_full.html` | The paper's coding results as results dashboards (open in a browser; no model, no network). |
| `data/threads.csv` | The 256 threads (`uid, so_question_id, link, author, created, text`), each rebuilt as it stood on 18 June 2023, code blocks as `[code]`. Stack Overflow content, CC BY-SA. |
| `data/ATTRIBUTION.md` | License, what we changed, and every thread's link and question author. |
| `data/splits.json` | The paper's split: 64 development threads, 192 evaluation threads (all reliability figures), the blind-pass and held-out samples, and the strata. |
| `results/approved_codebook_v1.2.json` | The approved codebook: 72 codes over five research questions, with definitions, include and exclude clauses, anchor quotes, provenance and the review log. |
| `results/L/`, `results/LJA/` | Lite coding (L) and Full coding after the coding adversaries (LJA), on all 256 threads: each coder's codes and one-line rationale (`coder_long.csv`), the 2-of-3 consensus, per-code reliability, prevalence and a summary. |
| `results/L_eval/`, `results/LJA_eval/` | The same, restricted to the 192 evaluation threads: the paper's reliability figures. (Their summaries list the development threads as "unknown uid": those threads were left out on purpose.) |
| `build_dashboards.py` | Rebuilds both dashboards from these files with this repository's own consensus and reliability code, and stops if any code's alpha differs from the paper's files. |
| `config.yaml`, `config.lite.yaml` | The experiment as pipeline configs, Full and Lite: the five research questions verbatim, issue codes, roster, thresholds, seed and split sizes. |
| `to_pipeline_csv.py` | Makes the pipeline's input (`corpus.csv`) from `data/`, adding the paper's strata so that `prepare` draws the paper's split; `--check` compares the splits. |
| `scoring/` | The experiment's scoring scripts against Zhang et al.'s labels (needs their spreadsheet; see below). |

Not here: Zhang et al.'s spreadsheet and labels (not ours to redistribute; use their paper and
dataset), the experiment's call log and raw model replies, and the researchers' own files. Model
names appear only as the paper gives them: Claude Opus 5 (coder 1), GPT-5.6 (coder 2) and Gemini
Flash 3.7 (coder 3), the families A, B and C at discovery.

## Look at the results (no model, no key)

Open `dashboard_lite.html` and `dashboard_full.html` in a browser (double-click them, or from the
repository folder: `open examples/zhang2023/dashboard_full.html` on macOS, `xdg-open ...` on Linux,
`start ...` on Windows). Each shows the reliability of every code, the codes below 0.67, prevalence
over the 256 threads, and the codebook with example quotes.

What you should see, on the 192 evaluation threads:

| | Lite | Full |
|---|---|---|
| Approved codes | 72 | 72 |
| Median Krippendorff's alpha | 0.77 | 0.87 |
| Codes below 0.67 (dropped by the authors) | 20 | 10 |
| Codes at or above 0.80 | 33 | 49 |
| Median cross-family kappa | 0.78 | 0.86 |

To rebuild them (a few seconds):

```bash
python3 examples/zhang2023/build_dashboards.py
```

## Run the pipeline yourself on these threads

This calls real models and costs money: in the paper, about $35 for Lite and $87 for Full on these
256 threads (about $14 and $34 per 100 threads). The threads are public, so no consent question
arises, but they still go to the vendors in your config.

1. Connect three model families (and, for Full, the decision model or not): follow `SETUP.md`.
   Edit the `models` block of `config.yaml` or `config.lite.yaml` to match what you have.
2. Make the pipeline's input and check your setup:
   ```bash
   python3 examples/zhang2023/to_pipeline_csv.py
   python3 pipeline/council.py --config examples/zhang2023/config.lite.yaml doctor
   ```
3. Prepare the corpus and confirm you have the paper's split:
   ```bash
   python3 pipeline/council.py --config examples/zhang2023/config.lite.yaml prepare
   python3 examples/zhang2023/to_pipeline_csv.py --check runs/zhang2023-lite
   ```
4. Run the stages with `--config examples/zhang2023/config.lite.yaml` (Lite) or
   `--config examples/zhang2023/config.yaml` (Full) as the README's "Scripted use" lists them,
   press the buttons in the app (open the config on its Start page), or ask a coding agent to follow
   `AGENTS.md`. The researchers' steps (blind pass, author review, held-out coding, spot-check, the
   decision on codes below 0.67) are yours.

Your numbers will not match the paper's exactly: models change, and this pipeline follows the
method as written where the experiment differed (below).

## How the experiment maps onto the pipeline

| Experiment | This repository |
|---|---|
| The corpus build: each of Zhang et al.'s 303 posts rebuilt as it stood on 18 June 2023 from the public Stack Exchange API (title, question, answers and comments by then; code as `[code]`); 256 still exist | `data/threads.csv` (the build itself needs Zhang et al.'s spreadsheet and network access, and is not included) |
| The split: seed 20260930; strata = tagged `github-copilot` or not x thread-length tercile; 64 development and 192 evaluation threads; blind pass 50 development threads; held out 60 evaluation threads | `data/splits.json`; `council.py prepare` with `config.yaml` (`strata_columns: [stratum]`, `held_out_min: 60`) draws the same sets; `to_pipeline_csv.py --check` verifies it |
| The experiment's scripts and briefs | `pipeline/` and `prompts/`, generalized and config-driven |
| `runs/lite/`, `runs/full/` | One workspace holding `reconciliation/lite/` and `reconciliation/full/`, `coding/L`, `coding/LJ`, `coding/LJA` |
| Conditions L, LJ, LJA (and two Lite reruns) | `run.py code` produces L, LJ, LJA. For a rerun, copy the workspace's `coding/L` aside and run Lite coding again. |
| Researchers' packets (blind pass, author review workbook and dashboard, held-out coding) | `pipeline/human.py`. The experiment's review dashboard had a locked tab showing Zhang et al.'s categories after the review was marked complete; the general dashboard has no such tab. |

## Scoring against Zhang et al.

Zhang et al.'s sheets carry no post id, so their labels are attributed to threads by text, and the
two codebooks are mapped onto each other from their definitions alone, before any council
assignment is seen. The scripts in `scoring/`, in order:

1. `attribute_labels_v2.py`: attributes every row of Zhang et al.'s five constant-comparison sheets
   to a thread (exact normalised substring, else a word n-gram score). The primary ground truth is
   the labels attributed to exactly one thread. Needs their spreadsheet.
2. Mapping a codebook onto their categories, by definitions only (no labelled thread, no council
   assignment): `map_codebook.py` (one mapper per research question), `map_debate.py` (two mappers,
   a debate on disagreeing cells, a judge), and `map_defensible.py` (the "defensible" mapping rule).
   An author audits every cell.
3. `support_scores.py`: the decision model's support for each code's cited threads.
4. `discovery_scores.py` and `codebook_scores.py`: agreement at the codebook stage (a code credited
   on the threads it cites).
5. `coding_scores.py`: agreement at the coding stage on evaluation threads (recall, same-question
   precision, F1, bootstrap intervals), the alpha distribution, survival, screening recall against
   Lite coding, and cost from the call log.

They read and write inside the experiment's folder (set `ZHANG_DEMO_ROOT` to it), and the mapping
and support scripts call models.

## Where this pipeline differs from what the experiment ran

These differences follow the method as written (the paper, Section 3); they mean a rerun will not
reproduce the published numbers exactly.

- **Codes below alpha 0.67 go to the researchers**, who refine and recode, or drop. In the
  experiment, 34 of 80 Lite-coded codes first fell below 0.67, returned to review, and were
  consolidated into codebook v1.2 (72 codes), after which all coding was rerun; the codes still
  below 0.67 were then dropped.
- **Verbatim quotes are checked exactly.** The experiment's validator accepted a quote that matched
  after normalizing case, whitespace and typographic punctuation; the method treats such a match as
  diagnostic only.
- **Discovery adversaries get grounding and omission leads together**, and the analyst's answer
  brief carries the removal rule. In the experiment the adversaries first had grounding leads only.
- **The coding adversary has a CONTEXT_CODED challenge type** when units carry context lines (not
  relevant here: threads have no separate context).
- **Decision-model state** includes the code's research question by default
  (`include_research_question`); `config.yaml` turns it off to match the experiment.
- **No decision model at reconciliation**, as in the experiment.
