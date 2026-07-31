# GPT-5.6-Terra Full-Corpus Measurement

- Generated: 2026-07-31T20:41:10Z
- Corpus: 32 OCR transcripts, 29,599 target records
- Runtime: Codex CLI 0.146.0
- Model: `gpt-5.6-terra`
- Reasoning effort: `xhigh`
- Protocol: one repository-denied, ephemeral Codex thread per document

This was an independent execution retained for representative usage, cost, and
quality diagnostics. It is not a released accuracy baseline and does not
replace the canonical GPT-5.5 or GPT-5.6-Sol results. The repository retains
the aggregate measurement, not a second exported prediction set.

All 32 jobs completed on their first attempt. The checker independently
recomputed the report from the saved predictions and ground truth before the
aggregate was recorded.

## Diagnostic quality

| Metric | Result |
| --- | ---: |
| Exact-record recall | 94.5% |
| Exact-record precision | 94.2% |
| Exact-record F1 | 94.4% |
| Complete documents | 5/32 (15.6%) |
| Field micro-F1 | 99.0% |
| Field macro-F1 | 98.4% |
| Predicted records | 29,687 |
| Execution errors | 0 |

The gap between 94.5% exact-record recall and 99.0% field micro-F1 is real.
For example, Terra added a fuel-band suffix to the `schedule` field on all 998
rows of `ifta_return_schedule_002`. Most row values remained correct, but no
row matched the requested record exactly. It also paraphrased description and
handler fields in the three long-range claim packets, producing zero exact
records there despite 91.5% field micro-F1 for that family.

## Measured usage

| Metric | Total |
| --- | ---: |
| Input tokens | 31,497,125 |
| Cached input tokens | 29,355,264 |
| Uncached input tokens | 2,141,861 |
| Cache-write input tokens | 0 |
| Output tokens | 365,763 |
| Reasoning output tokens | 186,644 |

Reasoning output tokens are included in output tokens and are not charged twice.

## Cost interpretation

Using the GPT-5.6-Terra ChatGPT rate card effective July 30, 2026 of 50
credits per million uncached input tokens, 5 credits per million cached input
tokens, and 300 credits per million output tokens:

`363.598270 credits`

This is consumption calculated from measured tokens. The run used a Codex
subscription, so it does not have a directly attributable per-run USD invoice.

At standard API list prices of $2.00 per million uncached input tokens, $0.20
per million cached input tokens, $2.50 per million cache-write tokens, and
$12.00 per million output tokens, the same usage corresponds to:

`$14.543931`

This uses short-context pricing. Codex CLI 0.146.0 caps Terra's active context
at 272K tokens and compacts before exceeding that window. Cumulative input over
the full agent turn can exceed 272K without any individual request entering
long-context pricing. The USD figure is an API list-price equivalent, not the
actual subscription charge.

## Distribution

- Mean: 11.362446 credits per document
- Median: 8.632175 credits per document
- Minimum: 2.929390 credits (`driver_schedule_sparse_001`)
- Maximum: 33.116500 credits (`loss_run_external_001`)

## Size-normalized cost

The corpus contains 29,599 target records across 1,773 PDF pages.

| Unit | ChatGPT credits | Short-context API equivalent |
| --- | ---: | ---: |
| Document | 11.362446 | $0.454498 |
| Target record | 0.012284 | $0.000491 |
| 1,000 target records | 12.284140 | $0.491366 |
| PDF page | 0.205075 | $0.008203 |
| 100 PDF pages | 20.507517 | $0.820301 |

Per-record cost varies with document structure:

| Family | Docs | Records | Pages | Credits / 1K records | API USD / 1K records | Credits / 100 pages |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| IFTA mileage by vehicle | 8 | 17,565 | 526 | 3.620408 | $0.144816 | 12.089821 |
| External loss runs | 3 | 900 | 129 | 97.235956 | $3.889438 | 67.839039 |
| Policy multi-hop | 3 | 1,344 | 340 | 57.166875 | $2.286675 | 22.597729 |
| Claim cross-page multi-hop | 3 | 77 | 308 | 489.943506 | $19.597740 | 12.248588 |

Most expensive documents:

| Document | Credits | Short-context API equivalent |
| --- | ---: | ---: |
| `loss_run_external_001` | 33.116500 | $1.324660 |
| `loss_run_external_002` | 28.628490 | $1.145140 |
| `multihop_bop_012_001` | 26.283130 | $1.051325 |
| `mixed_cgl_040_001` | 25.900570 | $1.036023 |
| `loss_run_external_003` | 25.767370 | $1.030695 |

## Verification

```bash
uv run pytest -q tests/test_codex_cost_measurement.py
```

The test reconciles per-document usage with the aggregate, recomputes both
cost figures, and checks that all input hashes match the GPT-5.5 and
GPT-5.6-Sol measurements.

References:

- https://learn.chatgpt.com/docs/pricing
- https://developers.openai.com/api/docs/pricing
- https://developers.openai.com/api/docs/changelog
