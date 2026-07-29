# Codex Full-Corpus Cost Measurements

These artifacts compare independent GPT-5.5 and GPT-5.6-Sol executions on the
same 32-document OCR corpus. Both runs used Codex CLI 0.145.0, `xhigh`
reasoning, four workers, one repository-denied ephemeral thread per document,
and the same prompts, field contracts, transcripts, and 272K context cap.

They are cost measurements, not accuracy baselines. The prediction sets and
evaluation reports are intentionally excluded; the released benchmark results
remain the only canonical accuracy results.

## Paired result

GPT-5.5 and GPT-5.6-Sol have the same ChatGPT credit and standard API rate
cards, so the cost difference below comes directly from measured token usage.

| Metric | GPT-5.5 | GPT-5.6-Sol | GPT-5.6 change |
| --- | ---: | ---: | ---: |
| Input tokens | 34,343,791 | 28,960,107 | -15.7% |
| Cached input tokens | 31,581,568 | 26,590,208 | -15.8% |
| Uncached input tokens | 2,762,223 | 2,369,899 | -14.2% |
| Output tokens | 463,004 | 277,190 | -40.1% |
| Reasoning output tokens | 223,331 | 127,310 | -43.0% |
| ChatGPT credits | 1,087.300475 | 836.507475 | -23.1% |
| Standard API equivalent | $43.492019 | $33.460299 | -23.1% |
| Credits / 1K target records | 36.734365 | 28.261342 | -23.1% |
| Credits / 100 PDF pages | 61.325464 | 47.180343 | -23.1% |

GPT-5.6-Sol used fewer credits on 26 of 32 paired documents. The median
per-document GPT-5.6/GPT-5.5 credit ratio was 0.7686.

This is one independent execution per model. Agent tool paths are stochastic,
so the result supports a representative efficiency observation, not a precise
causal estimate of the model-version effect. See the model-specific directories
for per-document usage and cost calculations.
