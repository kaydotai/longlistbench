# Multi-Model Evaluation Report

Generated: 2026-03-07 23:42:40

## Overall Results

| Model | Weighted F1 | Weighted Recall | Weighted Precision | Macro F1 | Rows | Samples | Errors |
|-------|-------------|-----------------|--------------------|----------|------|---------|--------|
| Gemini 2.5 (One-shot) | 5.7% | 2.9% | 92.0% | 5.7% | 500 | 1 | 0 |

Primary scores use corpus-level micro aggregation over all field-value pairs, so larger incident lists contribute proportionally more evidence than smaller documents.

## Results by Difficulty Tier

| Model | Easy | Medium | Hard | Extreme |
|-------|------|--------|------|---------|
| Gemini 2.5 (One-shot) | 0.0% | 0.0% | 0.0% | 5.7% |

## Results by Document Format

| Model | Detailed | Table |
|-------|----------|-------|
| Gemini 2.5 (One-shot) | 5.7% | 0.0% |

## Detailed Results

### extreme_100_001_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 (One-shot) | 5.7% | 2.9% | 92.0% | 16 | 26.4s |
