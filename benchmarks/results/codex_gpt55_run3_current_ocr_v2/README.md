# GPT-5.5 OCR Replicate 3

This directory contains the third of three matched GPT-5.5 full-corpus runs.
It uses the same 32 OCR transcripts, extraction contracts, Codex CLI 0.146.0
configuration, xhigh reasoning effort, repository-denied isolation, and scorer
as the other GPT-5.5 replicates.

| Documents | Target records | Errors | Exact-record recall | Complete documents | Field micro-F1 | API equivalent |
|---:|---:|---:|---:|---:|---:|---:|
| 32 | 29,599 | 0 | 94.8% | 7/32 | 99.1% | $42.07 |

All 32 document jobs completed successfully on their first attempt. No best-run
selection is used; the leaderboard statistic is the arithmetic mean of all
three runs.

The aggregate and links to every result package are in
`benchmarks/cost_measurements/gpt55_replicates_20260803/summary.json`.

Verify this run from the repository root:

```bash
python benchmarks/check_evaluation_report.py \
  --results-dir benchmarks/results/codex_gpt55_run3_current_ocr_v2 \
  --require-full-corpus
```
