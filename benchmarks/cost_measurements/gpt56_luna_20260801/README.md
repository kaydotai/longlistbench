# GPT-5.6-Luna Full-Corpus Measurement

- Generated: 2026-08-01T14:08:18Z
- Corpus: 32 OCR transcripts, 29,599 target records
- Runtime: Codex CLI 0.146.0
- Model: `gpt-5.6-luna`
- Reasoning effort: `xhigh`
- Protocol: one repository-denied, ephemeral Codex thread per document

This preselected execution supplies both the released Luna leaderboard result
and its measured usage. It was not chosen from the later repeats.

## Measured Usage

| Metric | Total |
|---|---:|
| Input tokens | 55,954,915 |
| Cached input tokens | 52,922,112 |
| Uncached input tokens | 3,032,803 |
| Output tokens | 582,442 |
| Reasoning output tokens | 312,587 |
| ChatGPT credits | 59.098331 |
| Standard API equivalent | $2.363933 |

The API equivalent applies the GPT-5.6-Luna short-context Standard rate card
effective July 30, 2026: $0.20 per million uncached input tokens, $0.02 per
million cached input tokens, and $1.20 per million output tokens. The active Codex
context is capped at 272K tokens, so the long-context surcharge does not apply.
The run used a subscription; `$2.36` is a rate-card equivalent, not an invoice.

The corresponding extraction reached 98.1% exact-record recall, 5/32 complete
documents, 99.5% field micro-F1, and 98.8% field macro-F1. Two matched repeats
show substantial strict-score stochasticity; see the adjacent replicate
summary rather than interpreting this single result as a stable expectation.

`usage_summary.json` contains the per-document token measurements, input
fingerprints, pricing calculation, and diagnostic evaluation values. It does
not include predictions or ground truth.
