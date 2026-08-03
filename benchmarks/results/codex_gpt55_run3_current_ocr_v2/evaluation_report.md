# Multi-Model Evaluation Report

Generated: 2026-08-03 19:41:22 UTC
Evaluation mode: `live`
Dataset manifest SHA-256: `ccf1881c256e9b5a2f575e73061d6fd40cfe763dc446bc873fc63cedd0019133`
Git SHA: `1d233ccb3fae185ed1840e77f16fa9a079cc5074`; dirty: `False`

## Overall Results

| Model | Exact-record recall | Complete documents | Field micro-F1 | Field macro-F1 | Rows | Samples | Errors | Time (s) | Cost (USD) |
|-------|---------------------|--------------------|----------------|----------------|------|---------|--------|----------|------------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 94.8% | 7/32 (21.9%) | 99.1% | 98.7% | 29599 | 32 | 0 | N/A | N/A |

The primary score is exact-record recall: a target counts only when every normalized field in one predicted record matches one ground-truth record. Complete-document success additionally requires the predicted and ground-truth record multisets to be identical. Record order is not scored. Field-pair F1 remains a secondary diagnostic.

## Strict Completeness by Evaluation Role

| Model | Structural Challenge | Scale Control |
|---|---|---|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 83.6% | 99.3% |

## Strict Completeness by Difficulty Tier

| Model | Core Operations | Claim Multihop | Policy Packets |
|---|---|---|---|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 95.4% | 0.0% | 89.2% |

## Strict Completeness by Document Format

| Model | Production Like Pdf | Crosspage |
|---|---|---|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 95.4% | 84.4% |

## Strict Completeness by Complexity Regime

| Model | Ifta Mileage By Vehicle | Ifta Multisection Return Packet | Ifta Return Schedule Details | Ifta Tax Return Summary | Driver Mvr Request And Roster | Loss Run External | Vehicle Schedule Spreadsheet Export | Ifta Tax Return Inquiry Detail | Driver Schedule Spreadsheet Export | Claim Crosspage Multihop | Policy Multi Hop |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 99.2% | 99.6% | 60.8% | 99.5% | 100.0% | 91.2% | 100.0% | 100.0% | 99.8% | 0.0% | 89.2% |

## Strict Completeness by Key Stressor

| Model | Ocr Layout Condition | Cross Section Join | Long Range Evidence | Heterogeneous Record List | Multi Column | Merged Cells | Multi Row | Duplicates | Distractor Sections | Repeated Keys | Large Doc | High Density Long List | Page Breaks | Businessowners Policy | Claimant Lookup | Class Code Payroll Rating | Coded Values | Commercial General Liability | Continuation Notes | Cross Page Join | Distractor Forms | Distractor Locations | Experience Mod And Schedule Rating | Exposure Rating Rows | Form Endorsement Links | Inherited Context | Layout Randomization | Limits Forms Exclusions | Location Scoped Coverage | Longer List | Many To One Policy | Material Clause Extraction | Mixed Layout | Mixed Prose Tables | Multiple Tables | Natural Long Range Join | Non Sequential Identifiers | Non Target Rows | Ocr Condition | Production Like Layout | Sparse Driver Fields | Split Records | Summary Distractors | Variable Policy Sections | Workers Compensation Policy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 99.6% | 99.6% | 84.4% | 89.2% | 84.4% | 93.7% | 98.0% | 84.5% | 87.0% | 99.6% | 94.6% | 95.4% | 94.8% | 85.8% | 0.0% | 98.9% | 0.0% | 83.8% | 91.2% | 0.0% | 83.8% | 83.8% | 98.9% | 83.8% | 85.8% | 86.8% | 85.9% | 83.8% | 85.8% | 0.0% | 0.0% | 89.2% | 0.0% | 0.0% | 95.0% | 84.4% | 0.0% | 86.8% | 94.8% | 95.4% | 91.2% | 87.4% | 91.2% | 91.2% | 98.9% |

## Strict Completeness by Transcript Condition

| Model | Canonical | OCR |
|-------|-----------|-----|
| Codex GPT-5.5 (CLI Agentic, xhigh) | N/A | 94.8% |

## Detailed Results

### driver_mvr_packet_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 100.0% | yes | 100.0% | 260 | N/A |

### driver_mvr_packet_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 100.0% | yes | 100.0% | 500 | N/A |

### driver_mvr_packet_003 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 100.0% | yes | 100.0% | 500 | N/A |

### driver_schedule_sparse_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 99.8% | no | 100.0% | 500 | N/A |

### ifta_mileage_by_vehicle_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 99.6% | no | 99.9% | 1159 | N/A |

### ifta_mileage_by_vehicle_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 94.7% | no | 99.1% | 2143 | N/A |

### ifta_mileage_by_vehicle_003 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 99.8% | no | 100.0% | 2195 | N/A |

### ifta_mileage_by_vehicle_004 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 100.0% | yes | 100.0% | 2239 | N/A |

### ifta_mileage_by_vehicle_005 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 99.7% | no | 99.9% | 2379 | N/A |

### ifta_mileage_by_vehicle_006 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 100.0% | yes | 100.0% | 2434 | N/A |

### ifta_mileage_by_vehicle_007 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 99.8% | no | 100.0% | 2445 | N/A |

### ifta_mileage_by_vehicle_008 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 100.0% | no | 100.0% | 2571 | N/A |

### ifta_multisection_return_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 99.7% | no | 100.0% | 335 | N/A |

### ifta_multisection_return_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 99.6% | no | 100.0% | 461 | N/A |

### ifta_return_schedule_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 95.9% | no | 99.5% | 582 | N/A |

### ifta_return_schedule_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 0.0% | no | 91.3% | 998 | N/A |

### ifta_return_schedule_005 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 95.5% | no | 99.5% | 1157 | N/A |

### ifta_tax_inquiry_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 100.0% | no | 98.9% | 665 | N/A |

### ifta_tax_inquiry_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 100.0% | no | 98.9% | 665 | N/A |

### ifta_tax_summary_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 99.3% | no | 99.9% | 760 | N/A |

### ifta_tax_summary_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 99.6% | no | 100.0% | 760 | N/A |

### loss_run_external_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 95.3% | no | 99.7% | 300 | N/A |

### loss_run_external_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 89.7% | no | 99.5% | 300 | N/A |

### loss_run_external_003 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 88.7% | no | 99.5% | 300 | N/A |

### mixed_040_001_crosspage (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 0.0% | no | 91.3% | 40 | N/A |

### mixed_cgl_040_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 83.8% | no | 98.1% | 567 | N/A |

### multihop_012_001_crosspage (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 0.0% | no | 94.1% | 12 | N/A |

### multihop_025_001_crosspage (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 0.0% | no | 95.7% | 25 | N/A |

### multihop_bop_012_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 85.8% | no | 97.7% | 364 | N/A |

### multihop_wc_025_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 98.9% | no | 96.9% | 494 | N/A |

### vehicle_schedule_sparse_001 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 100.0% | yes | 100.0% | 800 | N/A |

### vehicle_schedule_sparse_002 (ocr)

| Model | Exact records | Complete | Field F1 | Predicted | Time |
|-------|---------------|----------|----------|-----------|------|
| Codex GPT-5.5 (CLI Agentic, xhigh) | 100.0% | yes | 100.0% | 800 | N/A |
