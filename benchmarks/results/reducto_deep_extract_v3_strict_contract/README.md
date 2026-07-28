# Reducto Deep Extract v3 — Strict Contract

This directory contains the saved Reducto Deep Extract v3 predictions and
recomputable LongListBench report for the strict contract condition supplied
in `reducto_longlistbench_results.zip`.

## Protocol

- Input: the 32 raw LongListBench PDFs.
- Extractor: Reducto Deep Extract in agentic mode with
  `alpha.deep_extract_model: "v3"`.
- Prompt: the benchmark's generated no-leak extraction contract, with no
  additional prompt guidance.
- Scoring: the saved predictions are replayed through LongListBench's
  reference evaluator.
- Pricing: 3,099.268 Reducto credits across 1,773 processed pages. A dollar or
  per-token price was not supplied, so the leaderboard reports token price as
  unavailable.

The `ocr` segment in prediction filenames and report transcript fields is an
offline-scorer compatibility label; Reducto consumed raw PDFs, not the released
OCR transcripts.

## Result

| Documents | Target records | Predicted records | Errors | Exact recall | Exact F1 | Complete documents | Field F1 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 | 29,599 | 29,551 | 0 | 88.96% | 89.03% | 16/32 (50.0%) | 97.99% |

This is the comparable Reducto condition for the benchmark-generated
extraction contract. Its input modality still differs from the agentic CLI
rows, which consume released OCR transcripts.

## Provenance caveat

The supplied evaluation report records the correct released manifest hash but
also records `git_dirty: true` at source commit `a118b3cb`. The report and
predictions are preserved unchanged. Their metrics have been independently
recomputed against the current golden data and match exactly.

## Artifacts

- `*_predicted.json`: 32 saved per-document predictions.
- `*_reducto_meta.json`: per-document Reducto job, latency, usage, and record
  counts.
- `evaluation_report.json`: supplied aggregate and per-document metrics.
- `per_sample_status.tsv`: per-document success status.
- `run_metadata.json`: portable run-level provenance and usage totals.

## Verify

```bash
python benchmarks/check_evaluation_report.py \
  --results-dir benchmarks/results/reducto_deep_extract_v3_strict_contract \
  --require-full-corpus
```
