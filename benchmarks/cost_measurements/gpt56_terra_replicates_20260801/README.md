# GPT-5.6-Terra Stochasticity Check

Three independent full-corpus runs used the same 32 OCR transcripts, field
contracts, prompt, model, xhigh reasoning effort, Codex CLI 0.146.0, four
workers, and repository-denied isolation. All 96 document jobs completed on
their first attempt, and each report was independently recomputed from its
saved predictions and ground truth.

Run 1 was selected as the Terra leaderboard run before runs 2 and 3 were made.
The leaderboard therefore does not select the best or median repeat.

| Run | Exact recall | Complete docs | Field micro-F1 | Input tokens | Output tokens | API equivalent |
|---|---:|---:|---:|---:|---:|---:|
| 1, leaderboard | 94.5% | 5/32 | 99.0% | 31,497,125 | 365,763 | $14.54 |
| 2 | 94.5% | 7/32 | 99.1% | 34,121,637 | 402,077 | $15.32 |
| 3 | 98.1% | 6/32 | 99.6% | 34,646,953 | 361,477 | $15.17 |
| Median | 94.5% | 6/32 | 99.1% | 34,121,637 | 365,763 | $15.17 |

The large strict-recall range is concentrated in two 998- and 1,157-row IFTA
return schedules. Depending on the run, Terra either preserved the requested
schedule label or appended inherited fuel-band context. The latter left most
fields correct but invalidated every affected row under exact-record scoring.
Complete-document success varied less, from 5/32 to 7/32.

`summary.json` records the run-level metrics, usage, costs, and aggregate
statistics. Predictions for runs 2 and 3 remain ignored scratch artifacts;
only the preselected leaderboard run is released as a complete prediction set.
