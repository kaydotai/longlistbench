# Codex Full-Corpus Measurements

These artifacts compare GPT-5.5, GPT-5.6-Sol, GPT-5.6-Terra, and GPT-5.6-Luna
on the same 32-document OCR corpus. The GPT-5.5 and Sol measurements each use
one Codex CLI 0.145.0 run from July 29, 2026. Terra and Luna each use one
preselected leaderboard run plus two stochasticity repeats on CLI 0.146.0. All
use `xhigh` reasoning, four workers, one repository-denied ephemeral thread per
document, identical prompts, field contracts, transcripts, and the same 272K
context cap. Per-document input hashes match across models and repeats.

The GPT-5.5 and Sol artifacts are independent cost measurements with
non-canonical quality diagnostics. Terra and Luna run 1 are their respective
released leaderboard results and usage measurements; their full predictions
and reports are retained under `benchmarks/results/`.

## Four-model result

GPT-5.5 and GPT-5.6-Sol have the same rate cards, so their cost difference
comes directly from token usage. Terra and Luna use lower model-specific rate
cards, so their cost changes combine different usage with lower prices.

| Metric | GPT-5.5 | GPT-5.6-Sol | GPT-5.6-Terra | GPT-5.6-Luna | Luna vs Terra |
| --- | ---: | ---: | ---: | ---: | ---: |
| Input tokens | 34,343,791 | 28,960,107 | 31,497,125 | 55,954,915 | +77.7% |
| Cached input tokens | 31,581,568 | 26,590,208 | 29,355,264 | 52,922,112 | +80.3% |
| Uncached input tokens | 2,762,223 | 2,369,899 | 2,141,861 | 3,032,803 | +41.6% |
| Output tokens | 463,004 | 277,190 | 365,763 | 582,442 | +59.2% |
| Reasoning output tokens | 223,331 | 127,310 | 186,644 | 312,587 | +67.5% |
| ChatGPT credits | 1,087.300475 | 836.507475 | 363.598270 | 59.098331 | -83.7% |
| Standard API equivalent | $43.492019 | $33.460299 | $14.543931 | $2.363933 | -83.7% |
| Credits / 1K target records | 36.734365 | 28.261342 | 12.284140 | 1.996633 | -83.7% |
| Credits / 100 PDF pages | 61.325464 | 47.180343 | 20.507517 | 3.333239 | -83.7% |
| Exact-record recall (diagnostic) | 98.2% | 98.9% | 94.5% | 98.1% | +3.6 pp |
| Complete documents (diagnostic) | 6/32 | 8/32 | 5/32 | 5/32 | 0 docs |
| Field micro-F1 (diagnostic) | 99.6% | 99.8% | 99.0% | 99.5% | +0.5 pp |

GPT-5.6-Sol used fewer credits on 26 of 32 paired documents. The median
per-document GPT-5.6/GPT-5.5 credit ratio was 0.7686.

Terra cost fewer credits than both models on all 32 documents. Its median
per-document credit ratio was 0.4165 versus Sol and 0.3240 versus GPT-5.5. It
used 8.8% more total input and 32.0% more output tokens than Sol, so the 56.5%
cost reduction versus Sol is primarily a pricing result, not a token-efficiency
result. Against GPT-5.5, Terra used 8.3% fewer input and 21.0% fewer output
tokens and cost 66.6% less.

Terra's lower strict recall is concentrated in semantically sensitive fields.
It appended inherited fuel-band context to one 998-row schedule and paraphrased
fields in the long-range claim packets. The secondary field score remains high,
but the requested records are not exact.

Two additional Terra runs reached 94.5% and 98.1% exact-record recall, 7/32 and
6/32 complete documents, and API-equivalent costs of $15.32 and $15.17. Across
all three Terra runs, the median was 94.5% exact recall, 6/32 complete
documents, and $15.17. The range demonstrates stochasticity; it is not used to
replace the preselected leaderboard run.

Two additional Luna runs reached 93.8% and 91.4% exact-record recall, 6/32 and
4/32 complete documents, and API-equivalent costs of $2.62 and $2.26. Across
all three Luna runs, the median was 93.8% exact recall, 5/32 complete documents,
and $2.36. Run 1 consumed 77.7% more input and 59.2% more output tokens than
Terra run 1, but Luna's lower rates reduced API-equivalent cost by 83.7%.

GPT-5.5 and Sol still have one independent execution each, and Terra and Luna
used a newer CLI build. These results support representative cost-quality
observations, not precise causal estimates of model-version effects. See the
model-specific directories for per-document calculations and replicate
summaries.
