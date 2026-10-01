# Tiny demo: an invented corpus, run end to end offline

**The data here is invented for a demo.** `corpus.csv` holds 30 short, fictional answers of developers
to one survey question about a fictional AI coding assistant called "Quill". No real person wrote
them, and no finding should be drawn from them.

The demo runs the whole procedure in **Full** mode (adversaries and decision model on top of Lite)
with no model, no key and no network:

```bash
python3 pipeline/demo.py           # about five seconds; writes examples/tiny/workspace/
```

or press **Try the demo** in the local app (`python3 pipeline/app.py`, then http://127.0.0.1:8765/).

Then open in a browser:

- `workspace/dashboard.html`: the results dashboard
- `workspace/human/02_author_review/codebook_review.html`: the author review dashboard
- `workspace/RESULTS.md`: the report

## What is in this folder

| File | What it is |
|---|---|
| `corpus.csv` | The invented corpus (`uid,text`), 30 answers, two of them non-answers ("n/a", "same as above"). |
| `config.yaml` | The demo config: Full mode, two research questions (benefits; problems and concerns), every model and the decision model on the `replay` backend. |
| `config.manual.yaml` | The same study on the `manual` backend: the config the replies were recorded with. |
| `replay/` | 221 recorded replies (one per model call or decision-model request, for both coding rounds) and `index.json` (which prompt, by sha256, each reply answered). |
| `human_demo/` | Dummy files standing in for the researchers: blind-pass sheets, two reviewers' downloaded decisions, the negotiated edit log, resolved held-out labels, spot-check decisions for each coding round, and the decisions on the two codes below alpha 0.67. The reviewers **DEMO-A** and **DEMO-B** are fictional. |
| `workspace/` | The finished demo run (rebuilt by `pipeline/demo.py`). |

## How the replies were made

A coding agent (Claude Opus 5.5) followed `AGENTS.md` with `config.manual.yaml` and answered every
prompt the pipeline wrote to `manual/` itself, role-playing each role faithfully to its prompt and
output schema: three analysts, their three adversaries, the reconciler and its adversary, three
coders and their adversaries, and the decision model (giving plausible, uncalibrated
probabilities). The three "families" `alpha`, `beta` and `gamma` are therefore labels for that
role-play, not three vendors. A real study needs three model families (AGENTS.md, rule 3).

The coding replies were recorded a second time so that the three coders disagree on borderline
answers, as independent coders do (in the first recording they agreed on almost every answer, which
no real run does). For example, coder 2 leaves "losing my own skills" (R27) uncovered because the
code's label names only accepting suggestions blindly, and coders 2 and 3 read "I don't have to
search the web for syntax" (R26) as routine code and as an explanation, while coder 1 finds no code
for it. Each disagreement stays faithful to the coder's brief and to the invented answer.

The run exercises the paths a real run takes: a quote that failed the exact-substring check and was
repaired, a reading that left two answers unaccounted and got a completeness round, a v1 delta that
needed a repair, a quarantined adversary code that the reviewers admitted, codes that fell below the
three-unit floor at reconciliation, coding adversaries whose challenges the coders accept or reject,
and the low-reliability decision with both outcomes:

| Coding round | Lite coding (L) | Full, after the coding adversaries (LJA, the results) |
|---|---|---|
| Codebook 1.0 (10 codes) | median alpha 0.77; 3 codes below 0.67 | median alpha 0.84; 2 codes below 0.67: T08 (0.64), T10 (0.46) |
| Codebook 1.1 (9 codes), after the decision | median alpha 0.79 | median alpha 0.84; none below 0.67 |

The fictional researchers **refined T08** (its label and definition disagreed; it now reads
"Relying on it without understanding, or losing one's own skills") and **dropped T10** ("Reports
little or no net benefit"). `council.py refine` archived the first round to
`workspace/archive/codebook_v1.0/`, wrote codebook 1.1, and the whole corpus was coded again; the
results dashboard shows both rounds. The recode's replies are the files whose names end in
`__v1.1`.

To record your own manual run the same way: run it with `backend: manual`, then
`python3 pipeline/council.py --config <your config> export-replies --to replay`, and point a copy of
the config at `replay/` with `backend: replay` and `replay_dir: replay`.
