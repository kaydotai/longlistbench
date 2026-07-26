# Multi-Model Evaluation Report

Generated: 2026-07-26 03:59:31 UTC
Evaluation mode: `live`
Dataset manifest SHA-256: `ccf1881c256e9b5a2f575e73061d6fd40cfe763dc446bc873fc63cedd0019133`
Git SHA: `unknown`; dirty: `None`

## Overall Results

| Model | Exact-record recall | Complete documents | Field micro-F1 | Field macro-F1 | Rows | Samples | Errors | Time (s) | Cost (USD) |
|-------|---------------------|--------------------|----------------|----------------|------|---------|--------|----------|------------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 82.7% | 0/1 (0.0%) | 87.7% | 87.7% | 260 | 1 | 0 | N/A | N/A |

The primary score is exact-record recall: a target counts only when every normalized field in one predicted record matches one ground-truth record. Complete-document success additionally requires the predicted and ground-truth record multisets to be identical. Record order is not scored. Field-pair F1 remains a secondary diagnostic.

## Strict Completeness by Evaluation Role

| Model | Structural Challenge |
|---|---|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 82.7% |

## Strict Completeness by Difficulty Tier

| Model | Core Operations |
|---|---|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 82.7% |

## Strict Completeness by Document Format

| Model | Production Like Pdf |
|---|---|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 82.7% |

## Strict Completeness by Complexity Regime

| Model | Driver Mvr Request And Roster |
|---|---|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 82.7% |

## Strict Completeness by Key Stressor

| Model | Multi Row | High Density Long List | Page Breaks | Multiple Tables | Ocr Condition | Production Like Layout |
|---|---|---|---|---|---|---|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 82.7% | 82.7% | 82.7% | 82.7% | 82.7% | 82.7% |

## Strict Completeness by Transcript Condition

| Model | Canonical | OCR |
|-------|-----------|-----|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | N/A | 82.7% |

## Detailed Results

### driver_mvr_packet_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 82.7% | no | 87.7% | 268 | N/A |
