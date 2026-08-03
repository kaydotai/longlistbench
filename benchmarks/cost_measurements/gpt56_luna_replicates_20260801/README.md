# GPT-5.6-Luna Stochasticity Check

Three independent full-corpus runs used the same 32 OCR transcripts, field
contracts, prompt, model, xhigh reasoning effort, Codex CLI 0.146.0, four
workers, and repository-denied isolation. All 96 document jobs completed on
their first attempt, and each report was independently recomputed from its
saved predictions and ground truth.

The leaderboard reports the arithmetic mean and sample standard deviation
across all three runs. Run 1 remains the preselected reference execution; no
best-run selection is used.

| Run | Exact recall | Complete docs | Field micro-F1 | Input tokens | Output tokens | API equivalent | Result package |
|---|---:|---:|---:|---:|---:|---:|---|
| 1, reference | 98.1% | 5/32 | 99.5% | 55,954,915 | 582,442 | $2.36 | `codex_gpt56_luna_full_current_ocr_v2` |
| 2 | 93.8% | 6/32 | 99.0% | 67,810,321 | 568,985 | $2.62 | `codex_gpt56_luna_run2_current_ocr_v2` |
| 3 | 91.4% | 4/32 | 97.5% | 54,500,082 | 535,969 | $2.26 | `codex_gpt56_luna_run3_current_ocr_v2` |
| Mean ± SD | 94.4% ± 3.4 pp | 5.0 ± 1.0 / 32 | 98.7% ± 1.1 pp | 59,421,773 ± 7,301,023 | 562,465 ± 23,913 | $2.41 ± $0.18 | n=3 |

The strict-recall spread has identifiable document-level causes. In run 3,
two driver/MVR agents returned only 8 rows from 260- and 500-row targets even
though their files were valid. One return schedule in each of runs 2 and 3
preserved field values but used incompatible inherited labels, reducing exact
matches to zero. The CGL policy packet also varied materially in run 2. These
outcomes are counted, not retried or replaced.

`summary.json` records the run-level metrics, usage, costs, report hashes,
result-package paths, and aggregate statistics. All three prediction sets are
released and can be replayed with `benchmarks/check_replicate_summary.py`.
