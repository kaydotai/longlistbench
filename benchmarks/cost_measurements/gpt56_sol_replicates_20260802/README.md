# GPT-5.6-Sol Stochasticity Check

Three independent full-corpus runs used the same 32 OCR transcripts, field
contracts, prompt, model, xhigh reasoning effort, Codex CLI 0.146.0, four
workers, and repository-denied isolation. All 96 document jobs completed on
their first attempt, and each report was independently recomputed from its
saved predictions and ground truth.

The leaderboard reports the arithmetic mean and sample standard deviation
across all three runs. Run 1 is the preselected reference execution; no
best-run selection is used.

| Run | Exact recall | Complete docs | Field micro-F1 | Input tokens | Output tokens | API equivalent | Result package |
|---|---:|---:|---:|---:|---:|---:|---|
| 1, reference | 98.6% | 9/32 | 99.8% | 29,352,577 | 310,249 | $33.13 | `codex_gpt56_sol_run1_current_ocr_v2` |
| 2 | 98.8% | 8/32 | 99.7% | 31,171,378 | 313,588 | $35.33 | `codex_gpt56_sol_run2_current_ocr_v2` |
| 3 | 98.9% | 7/32 | 99.7% | 29,498,662 | 303,080 | $33.40 | `codex_gpt56_sol_run3_current_ocr_v2` |
| Mean ± SD | 98.8% ± 0.2 pp | 8.0 ± 1.0 / 32 | 99.7% ± 0.0 pp | 30,007,539 ± 1,010,557 | 308,972 ± 5,369 | $33.96 ± $1.20 | n=3 |

Exact-record recall varied by 0.3 percentage points across the runs. The main
remaining differences are in structural policy packets; all three runs reached
the same 99.5% exact recall on the 13 scale-control documents. Complete-document
success ranged from 7/32 to 9/32 because any missing, extra, or malformed record
fails the whole document.

`summary.json` records the run-level metrics, usage, costs, report hashes,
result-package paths, and aggregate statistics. All three prediction sets are
released and can be replayed with `benchmarks/check_replicate_summary.py`.
