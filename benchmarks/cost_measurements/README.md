# Codex Full-Corpus Measurements

These artifacts compare one independent GPT-5.5, GPT-5.6-Sol, and
GPT-5.6-Terra execution on the same 32-document OCR corpus. The GPT-5.5 and Sol
runs used Codex CLI 0.145.0 on July 29, 2026; Terra used CLI 0.146.0 on July 31.
All used `xhigh` reasoning, four workers, one repository-denied ephemeral
thread per document, identical prompts, field contracts, transcripts, and the
same 272K context cap. Per-document input hashes match across all three runs.

They are usage measurements with non-canonical quality diagnostics, not
accuracy baselines. The prediction sets and evaluation reports are
intentionally excluded; the released benchmark results remain the only
canonical accuracy results.

## Three-model result

GPT-5.5 and GPT-5.6-Sol have the same rate cards, so their cost difference
comes directly from token usage. Terra's July 30 rate card is 40% of their
uncached-input, cached-input, and output rates. Its cost change therefore
combines different usage with lower prices.

| Metric | GPT-5.5 | GPT-5.6-Sol | GPT-5.6-Terra | Terra vs Sol |
| --- | ---: | ---: | ---: | ---: |
| Input tokens | 34,343,791 | 28,960,107 | 31,497,125 | +8.8% |
| Cached input tokens | 31,581,568 | 26,590,208 | 29,355,264 | +10.4% |
| Uncached input tokens | 2,762,223 | 2,369,899 | 2,141,861 | -9.6% |
| Output tokens | 463,004 | 277,190 | 365,763 | +32.0% |
| Reasoning output tokens | 223,331 | 127,310 | 186,644 | +46.6% |
| ChatGPT credits | 1,087.300475 | 836.507475 | 363.598270 | -56.5% |
| Standard API equivalent | $43.492019 | $33.460299 | $14.543931 | -56.5% |
| Credits / 1K target records | 36.734365 | 28.261342 | 12.284140 | -56.5% |
| Credits / 100 PDF pages | 61.325464 | 47.180343 | 20.507517 | -56.5% |
| Exact-record recall (diagnostic) | 98.2% | 98.9% | 94.5% | -4.4 pp |
| Complete documents (diagnostic) | 6/32 | 8/32 | 5/32 | -3 docs |
| Field micro-F1 (diagnostic) | 99.6% | 99.8% | 99.0% | -0.7 pp |

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

This is one independent execution per model. Agent tool paths are stochastic,
and Terra used a newer CLI build, so the result supports a representative
cost-quality observation, not a precise causal estimate of model-version
effects. See the model-specific directories for per-document usage and cost
calculations.
