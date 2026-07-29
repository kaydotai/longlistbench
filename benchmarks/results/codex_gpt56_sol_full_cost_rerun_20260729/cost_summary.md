# Codex Full-Corpus Cost Rerun

- Generated: 2026-07-29T12:07:49Z
- Corpus: 32 OCR transcripts, 29,599 target records
- Runtime: Codex CLI 0.145.0
- Model: `gpt-5.6-sol`
- Reasoning effort: `xhigh`
- Protocol: one repository-denied, ephemeral Codex thread per document

## Measured usage

| Metric | Total |
| --- | ---: |
| Input tokens | 28,960,107 |
| Cached input tokens | 26,590,208 |
| Uncached input tokens | 2,369,899 |
| Cache-write input tokens | 0 |
| Output tokens | 277,190 |
| Reasoning output tokens | 127,310 |

Reasoning output tokens are included in output tokens and are not charged twice.

## Cost interpretation

Using the ChatGPT GPT-5.6-Sol rate card of 125 credits per million uncached
input tokens, 12.5 credits per million cached input tokens, and 750 credits per
million output tokens:

`836.507475 credits`

This is the consumption calculated from measured tokens. The run used a Codex
subscription, so it does not have a directly attributable per-run USD invoice.

At standard API list prices, the same measured token totals correspond to:

`$33.460299`

This uses short-context pricing. Codex CLI 0.145.0 caps the GPT-5.6-Sol active
context at 272K tokens and compacts the thread before it exceeds that window.
The API long-context surcharge applies only when a single request has more than
272K input tokens, so it cannot apply to this Codex run. Codex JSONL usage is
cumulative across the agent turn; cumulative input can exceed 272K without any
individual request entering long-context pricing. The USD figure is an API
list-price equivalent, not the actual subscription charge.

## Distribution

- Mean: 26.140859 credits per document
- Median: 18.078500 credits per document
- Minimum: 8.899100 credits (`driver_mvr_packet_001`)
- Maximum: 67.307225 credits (`multihop_wc_025_001`)

## Size-normalized cost

The corpus contains 29,599 target records across 1,773 PDF pages. Cost per
1,000 target records measures extraction throughput; cost per 100 pages
captures document-navigation burden.

| Unit | ChatGPT credits | Short-context API equivalent |
| --- | ---: | ---: |
| Document | 26.140859 | $1.045634 |
| Target record | 0.028261 | $0.001130 |
| 1,000 target records | 28.261342 | $1.130454 |
| Exactly recovered record | 0.028570 | $0.001143 |
| PDF page | 0.471803 | $0.018872 |
| 100 PDF pages | 47.180343 | $1.887214 |

Per-record cost varies materially by document structure:

| Family | Docs | Records | Pages | Credits / 1K records | API USD / 1K records | Credits / 100 pages |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| IFTA mileage by vehicle | 8 | 17,565 | 526 | 7.311855 | $0.292474 | 24.416868 |
| External loss runs | 3 | 900 | 129 | 196.500222 | $7.860009 | 137.093178 |
| Policy multi-hop | 3 | 1,344 | 340 | 131.305599 | $5.252224 | 51.904331 |
| Claim cross-page multi-hop | 3 | 77 | 308 | 1,120.694805 | $44.827792 | 28.017370 |

Claim cross-page packets look expensive per record because the task requires
navigating 308 pages to recover only 77 target records. Conversely, dense IFTA
tables are inexpensive per record despite their page count. Report both
normalizations rather than collapsing them into one average.

Most expensive documents:

| Document | Credits | Short-context API equivalent |
| --- | ---: | ---: |
| `multihop_wc_025_001` | 67.307225 | $2.692289 |
| `loss_run_external_002` | 63.125775 | $2.525031 |
| `loss_run_external_003` | 60.191350 | $2.407654 |
| `mixed_cgl_040_001` | 56.116100 | $2.244644 |
| `loss_run_external_001` | 53.533075 | $2.141323 |

## Extraction result

- Exact-record recall: 98.9189%
- Exact-record precision: 98.6955%
- Exact-record F1: 98.8071%
- Complete documents: 8/32
- Field micro-F1: 99.7562%
- Field macro-F1: 99.7092%

The released GPT-5.6-Sol run remains the public baseline. It recovered 28,971
records (97.8783%) and completed 8/32 documents. This independent rerun
recovered 29,279 records (98.9189%) and also completed 8/32 documents. Of the
308 additional exact matches, 298 came from policy packets, whose exact-record
recall changed from 73.3% to 95.5%. This is agent-strategy variance on the
hardest family, not a scorer change. The measured cost belongs to this rerun
and must not be attached to the released predictions.

## Verification

```text
OK: evaluation_report.json matches saved predictions + golden data
36 passed in 1.88s
```

Rate cards:

- https://learn.chatgpt.com/docs/pricing
- https://learn.chatgpt.com/docs/changelog
- https://developers.openai.com/api/docs/pricing
- https://developers.openai.com/api/docs/models/gpt-5.6-sol
