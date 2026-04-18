# Multi-Model Evaluation Report

Generated: 2026-03-08 21:27:53

## Overall Results

| Model | Weighted F1 | Weighted Recall | Weighted Precision | Macro F1 | Rows | Samples | Errors |
|-------|-------------|-----------------|--------------------|----------|------|---------|--------|
| Gemini 2.5 | 84.8% | 76.4% | 95.1% | 92.8% | 6828 | 80 | 0 |
| Gemini 2.5 (One-shot) | 27.4% | 15.9% | 97.8% | 68.5% | 6828 | 80 | 0 |

Primary scores use corpus-level micro aggregation over all field-value pairs, so larger incident lists contribute proportionally more evidence than smaller documents.

## Results by Difficulty Tier

| Model | Easy | Medium | Hard | Extreme |
|-------|------|--------|------|---------|
| Gemini 2.5 | 97.3% | 96.5% | 87.7% | 81.7% |
| Gemini 2.5 (One-shot) | 97.2% | 74.6% | 44.4% | 5.9% |

## Results by Document Format

| Model | Detailed | Table |
|-------|----------|-------|
| Gemini 2.5 | 71.0% | 95.9% |
| Gemini 2.5 (One-shot) | 27.0% | 27.8% |

## Detailed Results

### easy_10_001_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.2% | 97.2% | 97.2% | 10 | 11.9s |
| Gemini 2.5 (One-shot) | 97.2% | 97.2% | 97.2% | 10 | 0.0s |

### easy_10_001_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 99.7% | 99.7% | 99.7% | 10 | 12.4s |
| Gemini 2.5 (One-shot) | 99.7% | 99.7% | 99.7% | 10 | 0.0s |

### easy_10_002_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.2% | 97.2% | 97.2% | 10 | 11.2s |
| Gemini 2.5 (One-shot) | 97.2% | 97.2% | 97.2% | 10 | 0.0s |

### easy_10_002_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 99.7% | 99.7% | 99.7% | 10 | 11.9s |
| Gemini 2.5 (One-shot) | 99.7% | 99.7% | 99.7% | 10 | 0.0s |

### easy_10_003_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.2% | 97.2% | 97.2% | 10 | 11.1s |
| Gemini 2.5 (One-shot) | 97.2% | 97.2% | 97.2% | 10 | 0.0s |

### easy_10_003_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 100.0% | 100.0% | 100.0% | 10 | 13.4s |
| Gemini 2.5 (One-shot) | 100.0% | 100.0% | 100.0% | 10 | 0.0s |

### easy_10_004_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 92.6% | 88.4% | 97.2% | 10 | 11.6s |
| Gemini 2.5 (One-shot) | 92.6% | 88.4% | 97.2% | 10 | 0.0s |

### easy_10_004_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 94.7% | 90.4% | 99.4% | 10 | 11.1s |
| Gemini 2.5 (One-shot) | 98.2% | 98.2% | 98.2% | 11 | 0.0s |

### easy_10_005_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.2% | 97.2% | 97.2% | 11 | 12.6s |
| Gemini 2.5 (One-shot) | 92.6% | 88.4% | 97.2% | 10 | 0.0s |

### easy_10_005_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 95.2% | 90.9% | 100.0% | 10 | 11.2s |
| Gemini 2.5 (One-shot) | 100.0% | 100.0% | 100.0% | 11 | 0.0s |

### easy_10_006_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.2% | 97.2% | 97.2% | 10 | 11.5s |
| Gemini 2.5 (One-shot) | 97.2% | 97.2% | 97.2% | 10 | 0.0s |

### easy_10_006_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 99.7% | 99.7% | 99.7% | 10 | 11.2s |
| Gemini 2.5 (One-shot) | 100.0% | 100.0% | 100.0% | 10 | 0.0s |

### easy_10_007_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.2% | 97.2% | 97.2% | 10 | 13.5s |
| Gemini 2.5 (One-shot) | 97.2% | 97.2% | 97.2% | 10 | 0.0s |

### easy_10_007_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 99.7% | 99.7% | 99.7% | 10 | 11.5s |
| Gemini 2.5 (One-shot) | 99.7% | 99.7% | 99.7% | 10 | 0.0s |

### easy_10_008_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.2% | 97.2% | 97.2% | 10 | 12.8s |
| Gemini 2.5 (One-shot) | 97.2% | 97.2% | 97.2% | 10 | 0.0s |

### easy_10_008_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 100.0% | 100.0% | 100.0% | 10 | 12.0s |
| Gemini 2.5 (One-shot) | 95.0% | 95.0% | 95.0% | 10 | 0.0s |

### easy_10_009_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 92.6% | 88.4% | 97.2% | 10 | 11.1s |
| Gemini 2.5 (One-shot) | 92.6% | 88.4% | 97.2% | 10 | 0.0s |

### easy_10_009_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 95.2% | 90.9% | 100.0% | 10 | 11.8s |
| Gemini 2.5 (One-shot) | 100.0% | 100.0% | 100.0% | 11 | 0.0s |

### easy_10_010_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 92.6% | 88.4% | 97.2% | 10 | 11.5s |
| Gemini 2.5 (One-shot) | 97.2% | 97.2% | 97.2% | 11 | 0.0s |

### easy_10_010_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 100.0% | 100.0% | 100.0% | 11 | 16.4s |
| Gemini 2.5 (One-shot) | 95.2% | 90.9% | 100.0% | 10 | 0.0s |

### easy_10_011_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.2% | 97.2% | 97.2% | 10 | 13.5s |
| Gemini 2.5 (One-shot) | 97.2% | 97.2% | 97.2% | 10 | 0.0s |

### easy_10_011_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 100.0% | 100.0% | 100.0% | 10 | 11.4s |
| Gemini 2.5 (One-shot) | 100.0% | 100.0% | 100.0% | 10 | 0.0s |

### easy_10_012_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.2% | 97.2% | 97.2% | 10 | 11.9s |
| Gemini 2.5 (One-shot) | 97.2% | 97.2% | 97.2% | 10 | 0.0s |

### easy_10_012_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 99.7% | 99.7% | 99.7% | 10 | 11.8s |
| Gemini 2.5 (One-shot) | 99.7% | 99.7% | 99.7% | 10 | 0.0s |

### easy_10_013_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.2% | 97.2% | 97.2% | 10 | 12.1s |
| Gemini 2.5 (One-shot) | 97.2% | 97.2% | 97.2% | 10 | 0.0s |

### easy_10_013_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 100.0% | 100.0% | 100.0% | 10 | 11.9s |
| Gemini 2.5 (One-shot) | 100.0% | 100.0% | 100.0% | 10 | 0.0s |

### easy_10_014_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.2% | 97.2% | 97.2% | 11 | 12.7s |
| Gemini 2.5 (One-shot) | 97.2% | 97.2% | 97.2% | 11 | 0.0s |

### easy_10_014_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 95.2% | 90.9% | 100.0% | 10 | 12.1s |
| Gemini 2.5 (One-shot) | 95.2% | 90.9% | 100.0% | 10 | 0.0s |

### easy_10_015_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.2% | 97.2% | 97.2% | 11 | 12.7s |
| Gemini 2.5 (One-shot) | 92.6% | 88.4% | 97.2% | 10 | 0.0s |

### easy_10_015_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 95.2% | 90.9% | 100.0% | 10 | 11.8s |
| Gemini 2.5 (One-shot) | 95.2% | 90.9% | 100.0% | 10 | 0.0s |

### extreme_100_001_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 63.3% | 48.5% | 91.4% | 265 | 252.1s |
| Gemini 2.5 (One-shot) | 5.7% | 2.9% | 92.0% | 16 | 0.0s |

### extreme_100_001_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 94.7% | 94.9% | 94.5% | 502 | 524.3s |
| Gemini 2.5 (One-shot) | 5.7% | 2.9% | 91.7% | 16 | 0.0s |

### extreme_100_002_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 62.9% | 47.9% | 91.7% | 261 | 203.8s |
| Gemini 2.5 (One-shot) | 5.7% | 2.9% | 92.0% | 16 | 0.0s |

### extreme_100_002_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 93.9% | 93.9% | 93.9% | 500 | 482.6s |
| Gemini 2.5 (One-shot) | 6.2% | 3.2% | 99.7% | 16 | 0.0s |

### extreme_100_003_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 63.7% | 49.0% | 91.0% | 269 | 200.0s |
| Gemini 2.5 (One-shot) | 5.7% | 2.9% | 92.0% | 16 | 0.0s |

### extreme_100_003_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 95.0% | 94.9% | 95.1% | 499 | 510.1s |
| Gemini 2.5 (One-shot) | 6.2% | 3.2% | 99.7% | 16 | 0.0s |

### extreme_100_004_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 64.5% | 49.5% | 92.4% | 268 | 202.5s |
| Gemini 2.5 (One-shot) | 5.7% | 2.9% | 92.0% | 16 | 0.0s |

### extreme_100_004_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 96.9% | 97.0% | 96.8% | 501 | 406.7s |
| Gemini 2.5 (One-shot) | 6.2% | 3.2% | 99.8% | 16 | 0.0s |

### extreme_100_005_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 64.4% | 49.6% | 91.8% | 270 | 197.3s |
| Gemini 2.5 (One-shot) | 5.7% | 2.9% | 92.0% | 16 | 0.0s |

### extreme_100_005_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 96.5% | 96.6% | 96.4% | 501 | 456.7s |
| Gemini 2.5 (One-shot) | 6.2% | 3.2% | 99.7% | 16 | 0.0s |

### hard_50_001_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 78.2% | 65.4% | 97.2% | 37 | 34.0s |
| Gemini 2.5 (One-shot) | 43.8% | 28.3% | 97.2% | 16 | 0.0s |

### hard_50_001_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 98.5% | 98.5% | 98.5% | 55 | 59.8s |
| Gemini 2.5 (One-shot) | 45.1% | 29.1% | 100.0% | 16 | 0.0s |

### hard_50_002_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 72.9% | 58.3% | 97.2% | 33 | 34.4s |
| Gemini 2.5 (One-shot) | 43.8% | 28.3% | 97.2% | 16 | 0.0s |

### hard_50_002_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 92.0% | 92.0% | 92.0% | 55 | 51.0s |
| Gemini 2.5 (One-shot) | 42.8% | 27.6% | 95.0% | 16 | 0.0s |

### hard_50_003_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 75.3% | 63.6% | 92.1% | 38 | 33.0s |
| Gemini 2.5 (One-shot) | 43.8% | 28.3% | 97.2% | 16 | 0.0s |

### hard_50_003_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 98.1% | 98.1% | 98.1% | 55 | 51.5s |
| Gemini 2.5 (One-shot) | 44.9% | 29.0% | 99.7% | 16 | 0.0s |

### hard_50_004_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 79.5% | 67.2% | 97.2% | 38 | 33.6s |
| Gemini 2.5 (One-shot) | 43.8% | 28.3% | 97.2% | 16 | 0.0s |

### hard_50_004_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.0% | 96.2% | 97.9% | 54 | 48.7s |
| Gemini 2.5 (One-shot) | 45.1% | 29.1% | 100.0% | 16 | 0.0s |

### hard_50_005_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 80.7% | 68.9% | 97.2% | 39 | 34.8s |
| Gemini 2.5 (One-shot) | 43.8% | 28.3% | 97.2% | 16 | 0.0s |

### hard_50_005_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.4% | 95.6% | 99.2% | 53 | 48.7s |
| Gemini 2.5 (One-shot) | 46.9% | 30.7% | 99.3% | 17 | 29.0s |

### hard_50_006_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 78.2% | 65.4% | 97.2% | 37 | 33.6s |
| Gemini 2.5 (One-shot) | 43.8% | 28.3% | 97.2% | 16 | 0.0s |

### hard_50_006_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 95.5% | 94.6% | 96.4% | 54 | 53.5s |
| Gemini 2.5 (One-shot) | 47.1% | 30.9% | 99.8% | 17 | 0.0s |

### hard_50_007_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 78.2% | 65.4% | 97.2% | 37 | 34.4s |
| Gemini 2.5 (One-shot) | 43.8% | 28.3% | 97.2% | 16 | 0.0s |

### hard_50_007_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 92.1% | 89.6% | 94.8% | 52 | 51.9s |
| Gemini 2.5 (One-shot) | 42.1% | 27.2% | 93.4% | 16 | 0.0s |

### hard_50_008_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 79.4% | 67.1% | 97.1% | 38 | 33.8s |
| Gemini 2.5 (One-shot) | 43.8% | 28.3% | 97.2% | 16 | 28.7s |

### hard_50_008_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.9% | 97.9% | 97.9% | 55 | 52.1s |
| Gemini 2.5 (One-shot) | 45.0% | 29.0% | 99.8% | 16 | 29.8s |

### medium_25_001_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 95.4% | 93.6% | 97.2% | 26 | 28.3s |
| Gemini 2.5 (One-shot) | 72.4% | 57.6% | 97.2% | 16 | 28.4s |

### medium_25_001_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 95.9% | 92.4% | 99.8% | 25 | 27.1s |
| Gemini 2.5 (One-shot) | 74.4% | 59.3% | 100.0% | 16 | 28.8s |

### medium_25_002_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 100.0% | 100.0% | 100.0% | 25 | 26.8s |
| Gemini 2.5 (One-shot) | 78.0% | 64.0% | 100.0% | 16 | 27.5s |

### medium_25_002_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 98.7% | 98.7% | 98.7% | 25 | 27.6s |
| Gemini 2.5 (One-shot) | 78.0% | 64.0% | 100.0% | 16 | 28.8s |

### medium_25_003_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 96.2% | 92.6% | 100.0% | 25 | 27.9s |
| Gemini 2.5 (One-shot) | 72.4% | 57.6% | 97.2% | 16 | 28.7s |

### medium_25_003_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.8% | 97.8% | 97.8% | 27 | 31.7s |
| Gemini 2.5 (One-shot) | 72.7% | 57.9% | 97.7% | 16 | 27.3s |

### medium_25_004_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 93.5% | 90.0% | 97.2% | 25 | 28.2s |
| Gemini 2.5 (One-shot) | 72.4% | 57.6% | 97.2% | 16 | 27.3s |

### medium_25_004_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 99.3% | 99.3% | 99.3% | 27 | 29.0s |
| Gemini 2.5 (One-shot) | 74.4% | 59.3% | 100.0% | 16 | 27.9s |

### medium_25_005_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 93.5% | 90.0% | 97.2% | 25 | 27.0s |
| Gemini 2.5 (One-shot) | 72.4% | 57.6% | 97.2% | 16 | 27.3s |

### medium_25_005_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 99.1% | 99.1% | 99.1% | 27 | 28.0s |
| Gemini 2.5 (One-shot) | 74.4% | 59.3% | 100.0% | 16 | 27.3s |

### medium_25_006_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.1% | 97.1% | 97.1% | 25 | 27.4s |
| Gemini 2.5 (One-shot) | 77.9% | 63.9% | 99.8% | 16 | 27.8s |

### medium_25_006_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 99.9% | 99.9% | 99.9% | 25 | 29.6s |
| Gemini 2.5 (One-shot) | 78.0% | 64.0% | 100.0% | 16 | 27.3s |

### medium_25_007_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 93.5% | 90.0% | 97.2% | 25 | 27.1s |
| Gemini 2.5 (One-shot) | 70.3% | 56.0% | 94.4% | 16 | 27.1s |

### medium_25_007_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 98.3% | 98.3% | 98.3% | 27 | 28.0s |
| Gemini 2.5 (One-shot) | 74.4% | 59.3% | 100.0% | 16 | 26.8s |

### medium_25_008_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 93.5% | 90.0% | 97.2% | 25 | 28.7s |
| Gemini 2.5 (One-shot) | 72.4% | 57.6% | 97.2% | 16 | 27.4s |

### medium_25_008_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 100.0% | 100.0% | 100.0% | 27 | 29.9s |
| Gemini 2.5 (One-shot) | 74.4% | 59.3% | 100.0% | 16 | 29.4s |

### medium_25_009_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 93.5% | 90.0% | 97.2% | 25 | 26.6s |
| Gemini 2.5 (One-shot) | 72.4% | 57.6% | 97.2% | 16 | 26.8s |

### medium_25_009_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.0% | 95.2% | 98.8% | 26 | 28.0s |
| Gemini 2.5 (One-shot) | 77.1% | 62.9% | 99.8% | 17 | 27.3s |

### medium_25_010_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 97.2% | 97.2% | 97.2% | 25 | 26.7s |
| Gemini 2.5 (One-shot) | 78.7% | 66.1% | 97.2% | 17 | 27.7s |

### medium_25_010_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 98.3% | 98.3% | 98.3% | 25 | 27.5s |
| Gemini 2.5 (One-shot) | 77.8% | 63.8% | 99.7% | 16 | 27.4s |

### medium_25_011_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 93.5% | 90.0% | 97.2% | 25 | 26.5s |
| Gemini 2.5 (One-shot) | 74.4% | 59.3% | 100.0% | 16 | 28.5s |

### medium_25_011_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 95.4% | 95.4% | 95.4% | 27 | 28.2s |
| Gemini 2.5 (One-shot) | 77.3% | 63.0% | 100.0% | 17 | 27.7s |

### medium_25_012_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 93.5% | 90.0% | 97.2% | 25 | 27.5s |
| Gemini 2.5 (One-shot) | 74.4% | 59.3% | 100.0% | 16 | 26.6s |

### medium_25_012_table

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| Gemini 2.5 | 96.0% | 96.0% | 96.0% | 27 | 33.0s |
| Gemini 2.5 (One-shot) | 70.4% | 56.1% | 94.6% | 16 | 27.4s |
