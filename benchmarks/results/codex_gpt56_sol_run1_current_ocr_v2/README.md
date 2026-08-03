# GPT-5.6-Sol OCR Replicate 1

This directory contains the first of three matched GPT-5.6-Sol full-corpus
runs. It uses the same 32 OCR transcripts, extraction contracts, Codex CLI
0.146.0 configuration, xhigh reasoning effort, isolation policy, and scorer as
the other Sol runs.

| Documents | Target records | Errors | Exact-record recall | Complete documents | Field micro-F1 | Field macro-F1 |
|---:|---:|---:|---:|---:|---:|---:|
| 32 | 29,599 | 0 | 98.6% | 9/32 | 99.8% | 99.8% |

The three-run aggregate and links to every result package are in
`benchmarks/cost_measurements/gpt56_sol_replicates_20260802/summary.json`.

Verify this run from the repository root:

```bash
python benchmarks/check_evaluation_report.py \
  --results-dir benchmarks/results/codex_gpt56_sol_run1_current_ocr_v2 \
  --require-full-corpus
```
