# GPT-5.6-Terra Stochasticity Check

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
| 1, reference | 94.5% | 5/32 | 99.0% | 31,497,125 | 365,763 | $14.54 | `codex_gpt56_terra_full_current_ocr_v2` |
| 2 | 94.5% | 7/32 | 99.1% | 34,121,637 | 402,077 | $15.32 | `codex_gpt56_terra_run2_current_ocr_v2` |
| 3 | 98.1% | 6/32 | 99.6% | 34,646,953 | 361,477 | $15.17 | `codex_gpt56_terra_run3_current_ocr_v2` |
| Mean ± SD | 95.7% ± 2.0 pp | 6.0 ± 1.0 / 32 | 99.2% ± 0.3 pp | 33,421,905 ± 1,687,475 | 376,439 ± 22,306 | $15.01 ± $0.41 | n=3 |

The large strict-recall range is concentrated in two 998- and 1,157-row IFTA
return schedules. Depending on the run, Terra either preserved the requested
schedule label or appended inherited fuel-band context. The latter left most
fields correct but invalidated every affected row under exact-record scoring.
Complete-document success varied less, from 5/32 to 7/32.

`summary.json` records the run-level metrics, usage, costs, report hashes,
result-package paths, and aggregate statistics. All three prediction sets are
released and can be replayed with `benchmarks/check_replicate_summary.py`.
