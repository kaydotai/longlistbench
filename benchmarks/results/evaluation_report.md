# Multi-Model Evaluation Report

Generated: 2026-01-20 09:33:12

## Overall Results

| Model | Avg F1 | Avg Recall | Avg Precision | Samples | Errors |
|-------|--------|------------|---------------|---------|--------|
| GPT-4o | 89.1% | 87.8% | 90.6% | 3 | 0 |
| GPT-5.2 | 82.9% | 81.5% | 84.4% | 3 | 0 |
| Gemini 2.0 Flash | 86.5% | 85.0% | 88.1% | 3 | 0 |

## Results by Difficulty Tier

| Model | Easy | Medium | Hard | Extreme |
|-------|------|--------|------|---------|
| GPT-4o | 0.0% | 0.0% | 86.5% | 90.5% |
| GPT-5.2 | 0.0% | 0.0% | 80.9% | 83.8% |
| Gemini 2.0 Flash | 0.0% | 0.0% | 84.8% | 87.3% |

## Results by Document Format

| Model | Detailed | Table |
|-------|----------|-------|
| GPT-4o | 89.1% | 0.0% |
| GPT-5.2 | 82.9% | 0.0% |
| Gemini 2.0 Flash | 86.5% | 0.0% |

## Detailed Results

### hard_50_001_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| GPT-4o | 86.5% | 83.3% | 89.9% | 51 | 19.4s |
| GPT-5.2 | 80.9% | 77.2% | 84.9% | 50 | 0.0s |
| Gemini 2.0 Flash | 84.8% | 81.0% | 89.1% | 50 | 0.0s |

### extreme_100_001_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| GPT-4o | 90.3% | 89.9% | 90.7% | 496 | 0.0s |
| GPT-5.2 | 83.8% | 83.5% | 84.1% | 496 | 0.0s |
| Gemini 2.0 Flash | 86.4% | 86.2% | 86.7% | 497 | 0.0s |

### extreme_100_002_detailed

| Model | F1 | Recall | Precision | Predicted | Time |
|-------|-----|--------|-----------|-----------|------|
| GPT-4o | 90.6% | 90.1% | 91.2% | 494 | 1767.0s |
| GPT-5.2 | 83.9% | 83.7% | 84.1% | 498 | 1903.8s |
| Gemini 2.0 Flash | 88.2% | 88.0% | 88.5% | 497 | 1868.8s |
