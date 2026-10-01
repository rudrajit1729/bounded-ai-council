# 04 Coder's answer to the coding adversary (Stage 4; Full only)

## Purpose

The coder answers every challenge (ACCEPT, REJECT with a reason, PARTIAL) and writes its final
assignments for the batch. Its v0 file stays frozen; the revision is v1. Reliability is computed
on both: v0 as agreement among three independent coders, v1 as agreement among three
coder-adversary pipelines.

## Who receives it, and what it sees

- The original coder (same family and model), once per batch.
- Sees: the batch, its own frozen v0 file, the challenges, and the full codebook. Never sees
  another coder's files.

## Inputs

| Placeholder | Filled with |
|---|---|
| `{{CODER}}`, `{{VALID_CODES}}`, `{{ISSUE_IDS}}`, `{{CODEBOOK_VERSION}}`, `{{CODEBOOK}}` | as in 04_coder.md |
| `{{EXAMPLE_UID}}`, `{{EXAMPLE_CODE}}` | schema example |

## Output schema

Two outputs keyed by path, as in the prompt. The v1 file has the same format as v0.

<!-- BEGIN PROMPT -->
# Coder {{CODER}}: answering the coding adversary

An adversary has challenged your assignments. Answer every challenge and write your final
assignments. Only your final assignments enter consensus.

## Inputs

- `coding/batches/batch<N>.txt`: the batch named in your instruction.
- `coding/v0/coder{{CODER}}_batch<N>.jsonl`: your assignments (frozen; do not modify).
- `coding/challenges/coder{{CODER}}_batch<N>.json`: the challenges.
- The codebook below. Do not read any other coder's files.

## Outputs

1. `coding/answers/coder{{CODER}}_batch<N>.json`:

```json
{"coder": "{{CODER}}", "batch": 1,
  "answers": [{"challenge_id": "CC-01", "answer": "ACCEPT", "reason": "one sentence", "revision": "{{EXAMPLE_UID}} += {{EXAMPLE_CODE}}"}]}
```

`ACCEPT` (you changed the assignment as asked), `REJECT` (reason: the definition is not met /
the exclude clause applies / the quote does not say that), `PARTIAL`.

2. `coding/v1/coder{{CODER}}_batch<N>.jsonl`: your final assignments, same format as your v0
   file, one line per unit in batch order, incorporating accepted changes. If you reject every
   challenge it is a copy of your v0 file.

Valid code ids: {{VALID_CODES}}, plus {{ISSUE_IDS}}, UNCOVERED. Rationale (`why`) stays.
Write only these files.

## The codebook (closed, version {{CODEBOOK_VERSION}})

{{CODEBOOK}}
<!-- END PROMPT -->
