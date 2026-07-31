# Released GPT-5.6-Terra OCR Result

This directory contains the preselected GPT-5.6-Terra predictions and the
recomputable LongListBench leaderboard report.

## Protocol

- Input: one released Gemini OCR transcript per extraction.
- Extractor: Codex CLI 0.146.0 invoking `gpt-5.6-terra` at xhigh reasoning effort.
- Authentication: Codex subscription; credentials are not stored.
- Isolation: each extraction used a temporary workspace. A macOS sandbox denied the benchmark repository and additional parent paths; ground truth, target values and counts, and generator code were absent.
- Contract: claim runs received the published claim schema. Other runs received the public output shape plus sample-specific field names and record groups, but no field values or target counts.
- Tools: the agent could inspect the transcript, write temporary parsing code, validate its output, and save JSON.
- Scoring: predictions were replayed through the repository evaluator with the documented normalization rules.

## Result

| Documents | Target records | Errors | Exact-record recall | Complete documents | Field micro-F1 | Field macro-F1 |
|---:|---:|---:|---:|---:|---:|---:|
| 32 | 29,599 | 0 | 94.5% | 5/32 (15.6%) | 99.0% | 98.4% |

Exact-record recall requires every normalized target field to match.
Complete-document success requires an identical record multiset with no
missing or extra records; source order is not scored.

This run was selected before two additional stochasticity repeats were made.
Across all three matched runs, exact-record recall ranged from 94.5% to 98.1%
and complete-document success ranged from 5/32 to 7/32. The leaderboard does
not select the best repeat. The aggregate is under
`benchmarks/cost_measurements/gpt56_terra_replicates_20260801/`.

## Artifacts

- `*_predicted.json`: 32 saved per-document predictions.
- `evaluation_report.json`: machine-readable aggregate and per-document metrics.
- `evaluation_report.md`: human-readable report.
- `per_sample_status.tsv`: per-document exit status; all runs completed successfully.
- `run_metadata.json`: requested and observed model, effort, CLI version, transcript and contract fingerprints, token usage, and prediction hashes.

## Reproduce

```bash
python benchmarks/run_codex_cli_evaluation.py \
  --output-dir benchmarks/results/scratch/codex_gpt56_terra_reproduction \
  --model-key codex_gpt56_terra \
  --model gpt-5.6-terra \
  --effort xhigh \
  --workers 4 \
  --timeout-seconds 1800
```

## Verify

```bash
python benchmarks/check_evaluation_report.py \
  --results-dir benchmarks/results/codex_gpt56_terra_full_current_ocr_v2 \
  --require-full-corpus
```
