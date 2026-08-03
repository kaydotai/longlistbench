# Codex Full-Corpus Measurements

These artifacts compare GPT-5.5, GPT-5.6-Sol, GPT-5.6-Terra, and GPT-5.6-Luna
on the same 32-document OCR corpus. All four models have three matched
full-corpus leaderboard runs on Codex CLI 0.146.0. They use `xhigh` reasoning,
four workers, one repository-denied ephemeral thread per document, and the
same 272K context cap. All twelve packages have identical transcript,
field-contract, and prompt hashes.

The reference cost table below is retained as a historical single-run comparison
from an older CLI build; its GPT-5.5 and Sol accuracy diagnostics are not used
by the leaderboard. The leaderboard reports three-run arithmetic means and
sample standard deviations for all four Codex models. All twelve prediction
sets and reports are retained under `benchmarks/results/`.

## Reference-run cost comparison

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

The three fresh Sol runs reached 98.6%, 98.8%, and 98.9% exact-record recall,
completed 9/32, 8/32, and 7/32 documents, and had API-equivalent costs of
$33.13, $35.33, and $33.40. Their leaderboard means are 98.8% exact recall,
8.0/32 complete documents, and $33.96; the sample standard deviations are
0.2 pp, 1.0 document, and $1.20.

The three fresh GPT-5.5 runs reached 97.3%, 97.6%, and 94.8% exact-record
recall, completed 6/32, 6/32, and 7/32 documents, and had API-equivalent costs
of $40.55, $46.94, and $42.07. Their leaderboard means are 96.6% exact recall,
6.3/32 complete documents, and $43.19; the sample standard deviations are
1.5 pp, 0.6 document, and $3.34.

The other two Terra runs reached 94.5% and 98.1% exact-record recall, 7/32 and
6/32 complete documents, and API-equivalent costs of $15.32 and $15.17. Across
all three Terra runs, the mean was 95.7% exact recall, 6.0/32 complete
documents, and $15.01. The sample standard deviations were 2.0 pp, 1.0
document, and $0.41.

The other two Luna runs reached 93.8% and 91.4% exact-record recall, 6/32 and
4/32 complete documents, and API-equivalent costs of $2.62 and $2.26. Across
all three Luna runs, the mean was 94.4% exact recall, 5.0/32 complete documents,
and $2.41. The sample standard deviations were 3.4 pp, 1.0 document, and $0.18.
In the reference run pair, Luna consumed 77.7% more input and 59.2% more output
tokens than Terra, but its lower rates reduced API-equivalent cost by 83.7%.

The GPT-5.5/Sol cost pair uses an older CLI build than the replicated Sol,
Terra, and Luna runs. These results support representative cost-quality
observations, not precise causal estimates of model-version effects. See the
model-specific directories for per-document calculations and replicate
summaries.

Verify all twelve reports, predictions, fingerprints, and summary aggregates:

```bash
python benchmarks/check_replicate_summary.py
```
