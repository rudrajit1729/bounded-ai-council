# Worked example: the paper's experiment on Zhang et al. (2023)

The paper evaluates the procedure by running it on a public corpus that humans had already coded:
the Stack Overflow posts about GitHub Copilot that Zhang et al. (2023) analysed by constant
comparison (*Demystifying Practices, Challenges and Expected Features of Using GitHub Copilot*,
IJSEKE 33(11-12); dataset: Zenodo doi:10.5281/zenodo.8123303, CC BY 4.0). This folder shows how that
experiment maps onto this repository. It does not copy the experiment's data or results; it points to
them in the experiment folder (`demo_v2/` in the paper's project), whose analysis plan
(`demo_v2/ANALYSIS_PLAN.md`, fixed before the first model call, with dated addenda A1 to A17) is
the authoritative record of what was run.

Everything specific to Zhang et al. (their categories, the label attribution, the mapping between
codebooks, the agreement scores) lives here, not in `pipeline/`.

## Files

| File | What it is |
|---|---|
| `config.yaml` | The experiment as a pipeline config: Full mode, the five research questions verbatim with Zhang et al.'s published rationale, the two issue codes the experiment's coder brief used, the roster and model ids the call log records, Jev settings, thresholds, seed and split sizes. |
| `to_pipeline_csv.py` | Converts the experiment's corpus (`demo_v2/data/corpus.csv`) into the pipeline's input (`uid, text, stratum, link, ...`), carrying the experiment's strata so that `prepare` draws the same split; `--check` compares the splits. |
| `scoring/` | The experiment's scoring scripts, copied from `demo_v2/ground_truth/` with only the path set-up changed (set `ZHANG_DEMO_ROOT`). |

## How the experiment maps onto the pipeline

| Experiment (demo_v2) | This repository |
|---|---|
| `build_corpus.py`: rebuilds each of Zhang et al.'s 303 posts as it stood on 18 June 2023 from the public Stack Exchange API (title, question, answers and comments by then; code as `[code]`); 256 still exist | Not copied (it needs Zhang et al.'s spreadsheet and network access). Run it in `demo_v2/`, then `to_pipeline_csv.py`. |
| `make_splits.py`: seed 20260930; strata = tagged `github-copilot` or not x thread-length tercile; 64 development and 192 evaluation threads; blind pass 50 development threads; held out 60 evaluation threads | `council.py prepare` with `splits` in `config.yaml` (`strata_columns: [stratum]`, `held_out_min: 60`) draws the same sets from the same seed and strata; verify with `to_pipeline_csv.py --check`. |
| `council.py` + `run.py` + `models.py` | `pipeline/council.py`, `pipeline/run.py`, `pipeline/models.py` (generalized; config-driven; prompts in `prompts/`). |
| Briefs in `demo_v2/runs/full/briefs/` | `prompts/*.md`, generalized; `council.py` renders them with this config. |
| `runs/lite/`, `runs/full/` | One workspace (`runs/zhang2023/`) holding `reconciliation/lite/` and `reconciliation/full/`, `coding/L`, `coding/LJ`, `coding/LJA`. |
| Conditions L, LJ, LJA (and the Lite reruns L_rep2, L_rep3) | `run.py code` produces L, LJ, LJA. For reruns, copy the workspace's `coding/L` aside and run Lite coding again. |
| `human/` packets (blind pass, author review workbook and dashboard, held-out coding) | `pipeline/human.py` (blind-pass, review-dashboard, review-packet, review-to-edits, heldout-packet, spot-check). The experiment's dashboard had a locked tab showing Zhang et al.'s categories after the review was marked complete; the general dashboard has no such tab. |

## Scoring against Zhang et al.

Zhang et al.'s sheets carry no post id, so their labels are attributed to threads by text, and the
two codebooks are mapped onto each other from their definitions alone, before any council
assignment is seen. The scripts, in order:

1. `scoring/attribute_labels_v2.py`: attributes every row of Zhang et al.'s five constant-comparison
   sheets to a thread (exact normalised substring, else a word n-gram score), writing
   `ground_truth/human_labels.csv`. The primary ground truth is the labels attributed to exactly one
   thread (addendum A12). Needs their spreadsheet and the attribution helpers in `demo/ground_truth/`.
2. Mapping a codebook onto their categories, by definitions only (no labelled thread, no council
   assignment): `scoring/map_codebook.py` (one mapper per research question), `scoring/map_debate.py`
   (two mappers, a debate on disagreeing cells, a judge), and `scoring/map_defensible.py` (the
   "defensible" mapping rule, Claude and GPT mappers). An author audits every cell
   (`mapping_audit_*.csv`).
3. `scoring/support_scores.py`: the decision model's support for each code's cited threads (median
   below 0.5 marks a weakly supported code).
4. `scoring/discovery_scores.py` and `scoring/codebook_scores.py`: agreement at the codebook stage
   (a code credited on the threads it cites).
5. `scoring/coding_scores.py`: agreement at the coding stage on evaluation threads (recall,
   same-question precision, F1, bootstrap intervals with 1,000 resamples), the alpha distribution,
   survival, screening recall against Lite coding, and cost from the call log.

```bash
export ZHANG_DEMO_ROOT=/path/to/demo_v2          # the experiment folder
cd examples/zhang2023/scoring
python3 coding_scores.py "$ZHANG_DEMO_ROOT/ground_truth/mapping_def_v1.2.json"
```

The scripts read and write inside `ZHANG_DEMO_ROOT`, exactly as in the experiment; copy that folder
first if you want to keep the published results untouched. The mapping and support scripts call
models and the decision model through the experiment's own `models.py`.

## Rerunning the experiment with this pipeline

```bash
export ZHANG_DEMO_ROOT=/path/to/demo_v2
python3 examples/zhang2023/to_pipeline_csv.py
python3 pipeline/council.py --config examples/zhang2023/config.yaml prepare
python3 examples/zhang2023/to_pipeline_csv.py --check runs/zhang2023
# then follow AGENTS.md (Full mode) with --config examples/zhang2023/config.yaml
```

Model calls cost money and the corpus goes to the vendors named in the config. Model names follow
the paper's Section 5; the call log records the model id of every call.

## Where this pipeline differs from what the experiment ran

These differences follow the method as written (`overleaf/.../sections/03_procedure.tex`); they mean
a rerun will not reproduce the published numbers exactly.

- **Codes with alpha below 0.67 are dropped** from the results and listed in the supplement. In the
  experiment, 34 of 80 Lite-coded codes fell below 0.67, returned to review, and were consolidated
  into codebook v1.2 (72 codes), after which all coding was rerun (addendum A16).
- **Verbatim quotes are checked exactly.** The experiment's validator accepted a quote that matched
  after normalizing case, whitespace and typographic punctuation; the method treats such a match as
  diagnostic only. Duplicate unit ids in a code's list are errors here, warnings there.
- **Discovery adversaries get grounding and omission leads together**, and the analyst's answer brief
  carries the removal rule (remove a citation only when the unit clearly fails a named clause). In the
  experiment the adversaries first had grounding leads only; the omission leads and the removal rule
  were applied afterwards as a review of the diff (addendum A15).
- **The coding adversary has a CONTEXT_CODED challenge type** when units carry context lines (the
  method lists coded context among what the adversary challenges; Stack Overflow threads have no
  separate context, so it does not apply to this corpus).
- **Decision-model state** includes the code's research question by default
  (`include_research_question`); `config.yaml` turns it off to match the experiment.
- **No decision model at reconciliation**, as in the experiment after addendum A13.
