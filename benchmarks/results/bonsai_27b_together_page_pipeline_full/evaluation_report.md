# Multi-Model Evaluation Report

Generated: 2026-07-26 10:06:39 UTC
Evaluation mode: `saved_predictions`
Dataset manifest SHA-256: `ccf1881c256e9b5a2f575e73061d6fd40cfe763dc446bc873fc63cedd0019133`
Git SHA: `unknown`; dirty: `None`

## Overall Results

| Model | Exact-record recall | Complete documents | Field micro-F1 | Field macro-F1 | Rows | Samples | Errors | Time (s) | Cost (USD) |
|-------|---------------------|--------------------|----------------|----------------|------|---------|--------|----------|------------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 16.7% | 0/32 (0.0%) | 40.7% | 39.2% | 29599 | 32 | 0 | 796 | N/A |

The primary score is exact-record recall: a target counts only when every normalized field in one predicted record matches one ground-truth record. Complete-document success additionally requires the predicted and ground-truth record multisets to be identical. Record order is not scored. Field-pair F1 remains a secondary diagnostic.

## Strict Completeness by Evaluation Role

| Model | Structural Challenge | Scale Control |
|---|---|---|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 12.4% | 18.5% |

## Strict Completeness by Difficulty Tier

| Model | Core Operations | Claim Multihop | Policy Packets |
|---|---|---|---|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 17.6% | 0.0% | 0.0% |

## Strict Completeness by Document Format

| Model | Production Like Pdf | Crosspage |
|---|---|---|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 17.6% | 0.0% |

## Strict Completeness by Complexity Regime

| Model | Ifta Mileage By Vehicle | Ifta Multisection Return Packet | Ifta Return Schedule Details | Ifta Tax Return Summary | Driver Mvr Request And Roster | Loss Run External | Vehicle Schedule Spreadsheet Export | Ifta Tax Return Inquiry Detail | Driver Schedule Spreadsheet Export | Claim Crosspage Multihop | Policy Multi Hop |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 16.7% | 0.0% | 0.2% | 0.0% | 82.3% | 0.0% | 31.7% | 0.0% | 93.4% | 0.0% | 0.0% |

## Strict Completeness by Key Stressor

| Model | Ocr Layout Condition | Cross Section Join | Long Range Evidence | Heterogeneous Record List | Multi Column | Merged Cells | Multi Row | Duplicates | Distractor Sections | Repeated Keys | Large Doc | High Density Long List | Page Breaks | Businessowners Policy | Claimant Lookup | Class Code Payroll Rating | Coded Values | Commercial General Liability | Continuation Notes | Cross Page Join | Distractor Forms | Distractor Locations | Experience Mod And Schedule Rating | Exposure Rating Rows | Form Endorsement Links | Inherited Context | Layout Randomization | Limits Forms Exclusions | Location Scoped Coverage | Longer List | Many To One Policy | Material Clause Extraction | Mixed Layout | Mixed Prose Tables | Multiple Tables | Natural Long Range Join | Non Sequential Identifiers | Non Target Rows | Ocr Condition | Production Like Layout | Sparse Driver Fields | Split Records | Summary Distractors | Variable Policy Sections | Workers Compensation Policy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 12.6% | 18.1% | 0.0% | 0.0% | 0.0% | 13.8% | 17.6% | 16.7% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 9.9% | 12.8% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 16.9% | 0.0% | 0.0% | 9.9% | 16.7% | 17.6% | 0.0% | 10.0% | 0.0% | 0.0% | 0.0% |

## Strict Completeness by Transcript Condition

| Model | Canonical | OCR |
|-------|-----------|-----|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | N/A | 16.7% |

## Detailed Results

### driver_mvr_packet_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 71.5% | no | 86.9% | 230 | 6.1s |

### driver_mvr_packet_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 92.0% | no | 98.9% | 501 | 2.8s |

### driver_mvr_packet_003 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 78.2% | no | 89.5% | 444 | 4.9s |

### driver_schedule_sparse_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 93.4% | no | 96.8% | 500 | 0.0s |

### ifta_mileage_by_vehicle_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 5.5% | no | 19.6% | 162 | 1.7s |

### ifta_mileage_by_vehicle_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 17.9% | no | 53.9% | 1693 | 38.6s |

### ifta_mileage_by_vehicle_003 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 4.3% | no | 23.2% | 666 | 11.6s |

### ifta_mileage_by_vehicle_004 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 30.6% | no | 62.4% | 1676 | 35.4s |

### ifta_mileage_by_vehicle_005 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 17.4% | no | 39.6% | 900 | 4.8s |

### ifta_mileage_by_vehicle_006 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 17.1% | no | 57.2% | 1901 | 139.1s |

### ifta_mileage_by_vehicle_007 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 14.5% | no | 35.6% | 855 | 10.9s |

### ifta_mileage_by_vehicle_008 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 20.5% | no | 54.2% | 1771 | 31.5s |

### ifta_multisection_return_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 23.4% | 125 | 99.4s |

### ifta_multisection_return_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 32.6% | 270 | 28.2s |

### ifta_return_schedule_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.9% | no | 52.7% | 450 | 22.8s |

### ifta_return_schedule_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 8.8% | 114 | 12.5s |

### ifta_return_schedule_005 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 5.4% | 84 | 13.2s |

### ifta_tax_inquiry_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 17.6% | 488 | 3.0s |

### ifta_tax_inquiry_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 24.6% | 630 | 0.0s |

### ifta_tax_summary_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 6.0% | 42 | 10.6s |

### ifta_tax_summary_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 29.2% | 364 | 39.5s |

### loss_run_external_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 54.6% | 283 | 35.8s |

### loss_run_external_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 52.2% | 263 | 31.1s |

### loss_run_external_003 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 54.6% | 293 | 34.4s |

### mixed_040_001_crosspage (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 6.1% | 315 | 63.6s |

### mixed_cgl_040_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 6.4% | 109 | 7.0s |

### multihop_012_001_crosspage (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 4.6% | 107 | 22.5s |

### multihop_025_001_crosspage (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 10.5% | 101 | 21.8s |

### multihop_bop_012_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 10.0% | 90 | 11.7s |

### multihop_wc_025_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 0.0% | no | 18.9% | 208 | 8.5s |

### vehicle_schedule_sparse_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 42.6% | no | 74.7% | 591 | 28.4s |

### vehicle_schedule_sparse_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Ternary Bonsai 27B (Page Map-Reduce, Together) | 20.8% | no | 43.9% | 320 | 15.3s |
