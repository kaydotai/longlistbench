# GPT-5.6-Luna Stochasticity Check

Three independent full-corpus runs used the same 32 OCR transcripts, field
contracts, prompt, model, xhigh reasoning effort, Codex CLI 0.146.0, four
workers, and repository-denied isolation. All 96 document jobs completed on
their first attempt, and each report was independently recomputed from its
saved predictions and ground truth.

Run 1 was selected as the Luna leaderboard run before runs 2 and 3 were made.
The leaderboard therefore does not select the best or median repeat.

| Run | Exact recall | Complete docs | Field micro-F1 | Input tokens | Output tokens | API equivalent |
|---|---:|---:|---:|---:|---:|---:|
| 1, leaderboard | 98.1% | 5/32 | 99.5% | 55,954,915 | 582,442 | $11.82 |
| 2 | 93.8% | 6/32 | 99.0% | 67,810,321 | 568,985 | $13.09 |
| 3 | 91.4% | 4/32 | 97.5% | 54,500,082 | 535,969 | $11.31 |
| Median | 93.8% | 5/32 | 99.0% | 55,954,915 | 568,985 | $11.82 |

The strict-recall spread has identifiable document-level causes. In run 3,
two driver/MVR agents returned only 8 rows from 260- and 500-row targets even
though their files were valid. One return schedule in each of runs 2 and 3
preserved field values but used incompatible inherited labels, reducing exact
matches to zero. The CGL policy packet also varied materially in run 2. These
outcomes are counted, not retried or replaced.

`summary.json` records the run-level metrics, usage, costs, and aggregate
statistics. Predictions for runs 2 and 3 remain ignored scratch artifacts;
only the preselected leaderboard run is released as a complete prediction set.
