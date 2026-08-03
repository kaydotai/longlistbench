# GPT-5.6-Terra OCR Replicate 2

This directory contains the second of three matched GPT-5.6-Terra
full-corpus runs. It uses the same 32 OCR transcripts, extraction contracts,
Codex CLI 0.146.0 configuration, xhigh reasoning effort, isolation policy,
and scorer as the other Terra runs.

| Documents | Target records | Errors | Exact-record recall | Complete documents | Field micro-F1 | Field macro-F1 |
|---:|---:|---:|---:|---:|---:|---:|
| 32 | 29,599 | 0 | 94.5% | 7/32 | 99.1% | 98.8% |

The three-run aggregate and links to every result package are in
`benchmarks/cost_measurements/gpt56_terra_replicates_20260801/summary.json`.

Verify this run from the repository root:

```bash
python benchmarks/check_evaluation_report.py \
  --results-dir benchmarks/results/codex_gpt56_terra_run2_current_ocr_v2 \
  --require-full-corpus
```
