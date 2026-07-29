# GPT-5.5 Full-Corpus Cost Measurement

- Generated: 2026-07-29T18:43:13Z
- Corpus: 32 OCR transcripts, 29,599 target records
- Runtime: Codex CLI 0.145.0
- Model: `gpt-5.5`
- Reasoning effort: `xhigh`
- Protocol: one repository-denied, ephemeral Codex thread per document

This was an independent execution retained only for representative usage and
cost measurement. It is not the canonical accuracy run, is not exported to the
leaderboard, and must not be combined with the released run's 94.5% score. The
repository intentionally retains no second prediction set or evaluation
report.

## Measured usage

| Metric | Total |
| --- | ---: |
| Input tokens | 34,343,791 |
| Cached input tokens | 31,581,568 |
| Uncached input tokens | 2,762,223 |
| Cache-write input tokens | 0 |
| Output tokens | 463,004 |
| Reasoning output tokens | 223,331 |

Reasoning output tokens are included in output tokens and are not charged twice.

## Cost interpretation

Using the ChatGPT GPT-5.5 rate card of 125 credits per million uncached input
tokens, 12.5 credits per million cached input tokens, and 750 credits per
million output tokens:

`1,087.300475 credits`

This is the consumption calculated from measured tokens. The run used a Codex
subscription, so it does not have a directly attributable per-run USD invoice.

At standard API list prices, the same measured token totals correspond to:

`$43.492019`

This uses short-context pricing. Codex CLI 0.145.0 caps the GPT-5.5 active
context at 272K tokens and compacts the thread before it exceeds that window.
The API long-context surcharge applies only when a single request has more than
272K input tokens, so it cannot apply to this Codex run. Codex JSONL usage is
cumulative across the agent turn; cumulative input can exceed 272K without any
individual request entering long-context pricing. The USD figure is an API
list-price equivalent, not the actual subscription charge.

## Distribution

- Mean: 33.978140 credits per document
- Median: 26.231300 credits per document
- Minimum: 8.271025 credits (`driver_schedule_sparse_001`)
- Maximum: 100.641525 credits (`loss_run_external_001`)

## Size-normalized cost

| Unit | ChatGPT credits | Short-context API equivalent |
| --- | ---: | ---: |
| Document | 33.978140 | $1.359126 |
| Target record | 0.036734 | $0.001469 |
| 1,000 target records | 36.734365 | $1.469375 |
| PDF page | 0.613255 | $0.024530 |
| 100 PDF pages | 61.325464 | $2.453019 |

Per-record cost varies materially by document structure:

| Family | Docs | Records | Pages | Credits / 1K records | API USD / 1K records | Credits / 100 pages |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| IFTA mileage by vehicle | 8 | 17,565 | 526 | 11.618487 | $0.464739 | 38.798237 |
| External loss runs | 3 | 900 | 129 | 277.025167 | $11.081007 | 193.273372 |
| Policy multi-hop | 3 | 1,344 | 340 | 139.201749 | $5.568070 | 55.025632 |
| Claim cross-page multi-hop | 3 | 77 | 308 | 1,757.740909 | $70.309636 | 43.943523 |

Claim cross-page packets look expensive per record because the task requires
navigating 308 pages to recover only 77 target records. Conversely, dense IFTA
tables are inexpensive per record despite their page count. Report both
normalizations rather than collapsing them into one average.

Most expensive documents:

| Document | Credits | Short-context API equivalent |
| --- | ---: | ---: |
| `loss_run_external_001` | 100.641525 | $4.025661 |
| `loss_run_external_002` | 74.984650 | $2.999386 |
| `loss_run_external_003` | 73.696475 | $2.947859 |
| `mixed_cgl_040_001` | 72.223425 | $2.888937 |
| `multihop_bop_012_001` | 61.028575 | $2.441143 |

## Verification

```bash
uv run pytest -q tests/test_codex_cost_measurement.py
```

The test reconciles all per-document usage with the aggregate totals and
recomputes both cost figures from the recorded rate cards.

References:

- https://learn.chatgpt.com/docs/pricing
- https://learn.chatgpt.com/docs/changelog
- https://developers.openai.com/api/docs/pricing
- https://developers.openai.com/api/docs/models/gpt-5.5
