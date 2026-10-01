# Reporting checklist for a council run

What a report of a council run should contain, following the paper's reporting checklist (its
supplement, Appendix D), which is aligned with the community guidelines for empirical studies
involving language models (Baltes et al.). Items marked **Full** apply only when adversaries or the
decision model ran. The third column says where the pipeline puts each item; `RESULTS.md` (from
`council.py report`) collects most of them.

| Stage | Report | Where it comes from |
|---|---|---|
| Across the run | Model names, exact identifiers and dates; reasoning settings; the vendor mix, and its caveat when fewer than three families | `manifest.json` (settings), `logs/calls.jsonl` (model id and reasoning setting of every call), `RESULTS.md` section 1 |
| | Every brief verbatim and versioned | `briefs/` (rendered prompts), `prompts/` (templates) |
| | The call log: per call, model, settings, brief, ordered input manifest (hashes), output (hashes), tokens | `logs/calls.jsonl`, raw replies in `logs/raw/` |
| | The researchers involved at each stage (two or more) | `codebooks/approved_codebook.json` (`review.reviewed_by`); your write-up for the blind pass, held-out coding and spot-check |
| Preparation | Unit definition; context pairing; corpus size and blocks | `manifest.json`, `data/blocks.json` |
| | What was de-identified and how flagged units were checked; what left the machine, to which vendors, under which consent terms or agreement | `data_governance` in the config (you write it); `RESULTS.md` section 1 |
| 1 Discovery | Codes per analyst, with the layer of each; units read per analyst against corpus size; blocks, if any; units listed as uncodeable | `discovery/validation/v0_analyst_*.json`, `RESULTS.md` section 2 |
| | **Full**: challenges filed, accepted, partly accepted and rejected, per axis (semantic, latent, contrastive), type and analyst; quarantined codes proposed; decision-model lead counts | `discovery/challenges/`, `discovery/answers/`, `discovery/jev/`, `RESULTS.md` section 2 |
| Provenance check | Failures per discovery file (identifiers, quotes, support lists, counts) and their disposition; units unaccounted before and after the completeness round; confirmation that nothing with an error went forward | `discovery/validation/` (`per_reading/`, `repairs.json`, `v0_*`, `v1_*`) |
| 2 Reconciliation | Raw codes; groups; typed relations; codes dropped below the three-unit floor; contested merges; the provenance map | `codebooks/candidate_<cond>.json`, `reconciliation/<cond>/` |
| | **Full**: reconciliation adversary challenges and the reconciler's answers; Lite versus Full candidate codebooks | `reconciliation/full/adversary_challenges.json`, `reconciler_answers.json`, `codebooks/candidate_lite.json` |
| 3 Author review | Reviewers; the blind pass (sample size, seed, strata) and the codes it found that the council lacked, or the retention rate where the researchers coded first | `data/splits.json`, `review.blind_pass_codes_missing`, `results/retention.json` |
| | Edits by type with reasons; quarantined codes admitted; codebook version | `codebooks/approved_codebook.json` (`review.log`) |
| | **Full**: how the challenge logs were read | your write-up; the dashboard shows each code's challenges |
| 4 Coding | Coders; batch size and batches; issue and uncovered counts | `coding/manifest.json`, `results/<cond>/summary.json` |
| | **Full**: coding adversary challenges, acceptance per coder, cells changed v0 to v1 | `coding/LJA/`, `results/v0_v1_diff.json`, `RESULTS.md` section 5 |
| | **Full**: the decision model: thresholds, top-k, audit share and seed, screening recall against Lite coding, uncertain assignments; calibration sample and per-code metrics if you recalibrated | `coding/LJ/screening_plan.json`, `RESULTS.md` sections 5 and 6, `human/05_spot_check/` |
| 5 Reliability and consensus | Per-code prevalence, agreement counts (2x2), positive and negative agreement, alpha and pairwise kappa | `results/<cond>/reliability.csv`, `prevalence.csv`, `reliability_report.md` |
| | The distribution across codes: median, minimum, maximum, number below 0.67, number at or above 0.80 (no interval on the median) | `results/<cond>/summary.json`, `RESULTS.md` section 6 |
| | **Codes with alpha below 0.67**, with their definitions and agreement counts, and the researchers' decision for each (refined and recoded, or dropped) | `results/<cond>/reliability_report.md` ("Codes dropped from the results"), the decisions in `human/06_low_alpha/decisions.csv`, earlier rounds in `archive/`; `dashboard.html` |
| | Cross-family kappa when two coders share a family | `summary.json` (`cross_family_kappa_median`) |
| | Survival rate; retention where humans coded first | `summary.json` (`survival`), `results/retention.json` |
| | Human-council agreement on the held-out sample (at least 50 evaluation units, coded by at least two researchers without model assignments, differences resolved) | `results/human_council_agreement.json` |
| | The researchers' spot-check of rationales (sample size; issue-coded units, uncovered content; **Full**: decision-model disagreements and uncertain assignments) | `human/05_spot_check/decisions.csv` |
| | **Full**: alpha before and after the adversaries, the second labelled as agreement among coder-adversary pipelines | `results/LJ/` and `results/LJA/`, `RESULTS.md` section 6 |
| Output: themes | How the researchers grouped codes into themes, and the negative cases | your write-up |
| | Confirmation that every quotation in the write-up was machine-checked as an exact substring of its source | `council.py check-quotes WRITEUP.md` |
| Cost | Calls, tokens and dollars at dated list prices per stage, model calls and decision-model requests apart | `results/costs.csv` (`council.py cost`; prices in the config), `RESULTS.md` section 8, `dashboard.html` |
| Artifacts | Where the briefs, discovery files, challenge logs, review log, coded batches and reliability tables are published | the workspace folder; publish it with the paper when the data's terms allow |

## Before you release this repository

- [ ] Reserve a DOI and fill it in `CITATION.cff` and `README.md`.
- [ ] Confirm the copyright holders in `LICENSE` and the license of the prompts and documentation.
- [ ] Replace the placeholder model ids in `config.example.yaml` with ones you have run.
