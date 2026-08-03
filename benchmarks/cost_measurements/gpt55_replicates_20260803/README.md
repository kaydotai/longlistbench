# GPT-5.5 Stochasticity Check

Three independent full-corpus runs used the same 32 OCR transcripts, field
contracts, prompt, model, xhigh reasoning effort, Codex CLI 0.146.0, four
workers per run, and repository-denied isolation. All 96 document jobs
completed on their first attempt, and each report was independently recomputed
from its saved predictions and ground truth.

The aggregate uses the arithmetic mean and sample standard deviation across all
three runs. Run 1 was preselected as the reference execution; no best-run
selection is used.

| Run | Exact recall | Complete docs | Field micro-F1 | Input tokens | Output tokens | API equivalent | Result package |
|---|---:|---:|---:|---:|---:|---:|---|
| 1, reference | 97.3% | 6/32 | 99.1% | 30,287,815 | 433,442 | $40.55 | `codex_gpt55_run1_current_ocr_v2` |
| 2 | 97.6% | 6/32 | 99.5% | 37,592,399 | 471,957 | $46.94 | `codex_gpt55_run2_current_ocr_v2` |
| 3 | 94.8% | 7/32 | 99.1% | 33,517,639 | 454,338 | $42.07 | `codex_gpt55_run3_current_ocr_v2` |
| Mean ± SD | 96.6% ± 1.5 pp | 6.3 ± 0.6 / 32 | 99.3% ± 0.3 pp | 33,799,284 ± 3,660,428 | 453,246 ± 19,281 | $43.19 ± $3.34 | n=3 |

Structural exact recall averaged 89.5% ± 5.1 pp; the 13-document scale-control
slice averaged 99.4% ± 0.1 pp. Across all three runs the measured total was
3,238.881575 ChatGPT credits, corresponding to $129.555263 at standard API
list prices. These are usage equivalents for subscription-authenticated Codex
runs, not a per-run invoice.

The three replicate runners overlapped in wall-clock execution at the user's
request. Each document still used its own ephemeral Codex thread, separate
workspace, logs, predictions, and provenance. No run emitted a rate-limit
error, retry, timeout, or failed document.

`summary.json` records the run-level metrics, usage, costs, report hashes,
result-package paths, and aggregate statistics. All three prediction sets are
retained for independent replay.
