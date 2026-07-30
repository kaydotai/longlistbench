# Reducto Deep Extract v3 — Targeted Prompt

This directory contains the saved Reducto Deep Extract v3 predictions and
recomputable LongListBench report for the targeted-fields condition supplied
in `reducto_longlistbench_results.zip`.

## Protocol

- Input: the 32 raw LongListBench PDFs.
- Extractor: Reducto Deep Extract in agentic mode with
  `alpha.deep_extract_model: "v3"`.
- Prompt: the benchmark's generated no-leak extraction contract plus
  additional atomic-value, field-granularity, and identifier-label guidance.
- Scoring: the saved predictions are replayed through LongListBench's
  reference evaluator.
- Pricing: 3,108.063 Reducto credits across 1,773 processed pages, converted
  to $46.62 at the $0.015/credit Standard list rate observed on 2026-07-28.

The `ocr` segment in prediction filenames and report transcript fields is an
offline-scorer compatibility label; Reducto consumed raw PDFs, not the released
OCR transcripts.

## Result

| Documents | Target records | Predicted records | Errors | Exact recall | Exact F1 | Complete documents | Field F1 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 | 29,599 | 29,543 | 0 | 95.98% | 96.07% | 16/32 (50.0%) | 98.79% |

This prompt was developed after observing benchmark failure modes. It contains
no gold values, but it is test-set prompt engineering and is therefore listed
separately from the strict-contract result rather than presented as an
identical-prompt comparison.

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
  --results-dir benchmarks/results/reducto_deep_extract_v3_targeted_prompt \
  --require-full-corpus
```
