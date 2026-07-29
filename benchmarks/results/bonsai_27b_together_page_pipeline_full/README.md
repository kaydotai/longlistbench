# Released Ternary Bonsai 27B Page-Pipeline OCR Baseline

This directory contains the saved predictions and recomputable current
LongListBench report for the hosted Ternary Bonsai 27B page map-reduce
pipeline.

## Protocol

- Input: one released Gemini OCR transcript per extraction.
- Extractor: each OCR page is sent independently to
  `Prism-ML/Ternary-Bonsai-27B` with a strict JSON schema.
- Reconciliation: page candidates are grouped by record identity.
  Complete non-conflicting groups merge deterministically; ambiguous or
  incomplete groups use a schema-constrained model reduction.
- Hosting: Together's OpenAI-compatible endpoint. The API key is read from
  `TOGETHER_API_KEY` and is not stored.
- Scoring: saved predictions are replayed through the repository evaluator
  with the documented normalization rules.

## Result

| Documents | Target records | Predicted records | Errors | Exact-record recall | Complete documents | Field micro-F1 | Field macro-F1 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 | 29,599 | 16,546 | 0 | 16.7% | 0/32 (0.0%) | 40.7% | 39.2% |

Exact-record recall requires every normalized target field to match.
Complete-document success requires an identical record multiset with no
missing or extra records; source order is not scored.

## Artifacts

- `*_predicted.json`: 32 saved per-document predictions.
- `evaluation_report.json`: machine-readable aggregate and per-document
  metrics.
- `evaluation_report.md`: human-readable report.
- `per_sample_status.tsv`: per-document execution status.
- `run_metadata.json`: model, transcript, timing, token, and prediction-hash
  metadata.

Page and reduction checkpoints are runtime caches and are intentionally not
part of the released result directory.

## Reproduce

```bash
python benchmarks/run_bonsai_page_evaluation.py \
  --output-dir benchmarks/results/bonsai_27b_together_page_pipeline_full \
  --model-key bonsai_27b_together_page_pipeline \
  --model Prism-ML/Ternary-Bonsai-27B \
  --endpoint https://api.together.xyz/v1 \
  --api-key-env TOGETHER_API_KEY \
  --page-workers 4 \
  --reduction-workers 4
```

## Verify

```bash
python benchmarks/check_evaluation_report.py \
  --results-dir benchmarks/results/bonsai_27b_together_page_pipeline_full \
  --require-full-corpus
```
