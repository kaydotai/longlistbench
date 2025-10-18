# Lost-and-Found Entities Benchmark Dataset

This is the official benchmark dataset for evaluating long-list entity extraction from semi-structured insurance claims documents.

## Dataset Overview

- **Total Instances**: 80 benchmark PDFs (40 pairs in 2 formats)
- **Total Claims**: 2,700 insurance claim records
- **Domain**: Trucking insurance loss runs
- **Formats**: 2 document layouts (detailed + table)
- **Format**: PDF documents with ground truth JSON annotations
- **OCR Applied**: Yes (simulates real-world extraction scenarios)

## Difficulty Tiers

| Tier | Claims/PDF | Instances | Total Claims | Problems | Use Case |
|------|------------|-----------|--------------|----------|----------|
| **Easy** | 10 | 30 (15×2) | 300 | 1-2 | Quick validation, debugging |
| **Medium** | 25 | 24 (12×2) | 600 | 3-4 | Standard evaluation |
| **Hard** | 50 | 16 (8×2) | 800 | 5-6 | Stress testing |
| **Extreme** | 100 | 10 (5×2) | 1000 | All 7 | Production-scale scenarios |

Each difficulty tier includes instances in both **detailed** and **table** formats.

## Problem Types

The benchmark includes these real-world document complexity issues (**all 7 are fully implemented**):

1. **Page Breaks** - Table rows split across page boundaries
2. **Multi-row Entities** - Cells with line breaks (addresses, descriptions)
3. **Exact Duplicates** - Identical claim records appearing multiple times
4. **Large Documents** - High volume of records (100+ claims)
5. **Multiple Tables** - Relevant claims mixed with irrelevant content
6. **Multi-column Layout** - Research paper style formatting
7. **Merged Cells** - Cells spanning multiple columns/rows (table format)

Different problem combinations are used across instances to test extraction robustness. The **table format** is particularly effective for testing merged cells (Problem 7), while the **detailed format** tests complex multi-section layouts.

## File Naming Convention

```
{tier}_{claims}_{instance}_{format}.{ext}

Examples:
  easy_10_001_detailed.json       # Ground truth for easy tier, instance 1, detailed format
  easy_10_001_detailed.pdf        # PDF to extract from (detailed)
  easy_10_001_table.json          # Ground truth for easy tier, instance 1, table format
  easy_10_001_table.pdf           # PDF to extract from (table)
  medium_25_005_detailed.json     # Ground truth for medium tier, instance 5, detailed
  medium_25_005_table.pdf         # PDF for medium tier, instance 5, table format
```

### Format Descriptions

- **`_detailed`**: Incident sections with detailed line items, descriptions, and financial breakdowns
- **`_table`**: Compact tabular format with all claims as rows in a single table

## Ground Truth Schema

Each JSON file contains an array of claim objects with the following fields:

```json
{
  "incident_number": "#30001",
  "reference_number": "L230001",
  "company_name": "Lake Phillip Express",
  "division": "General",
  "coverage_type": "Physical Damage | Liability | Inland Marine",
  "status": "Open | Closed",
  "policy_number": "L23A4089",
  "policy_state": "GA",
  "cause_code": null,
  "description": "Incident description",
  "handler": "Claims Adjuster",
  "unit_number": "2024 VO 572389",
  "date_of_loss": "04/24/2023",
  "loss_state": "MO",
  "date_reported": "07/22/2023",
  "agency": "Agency Name",
  "insured": "Company Name",
  "claimants": ["Name 1", "Name 2"],
  "driver_name": "Last, First",
  "bi": {
    "reserve": 0.0,
    "paid": 0.0,
    "recovered": 0.0,
    "total_incurred": 0.0
  },
  "pd": {
    "reserve": 94972.41,
    "paid": 0.0,
    "recovered": 0.0,
    "total_incurred": 94972.41
  },
  "lae": {
    "reserve": 0.0,
    "paid": 0.0,
    "recovered": 0.0,
    "total_incurred": 0.0
  },
  "ded": {
    "reserve": 0.0,
    "paid": 0.0,
    "recovered": 2237.62,
    "total_incurred": -2237.62
  },
  "adjuster_notes": "Optional notes"
}
```

### Financial Fields

- **BI** (Bodily Injury): Medical expenses, pain and suffering
- **PD** (Property Damage): Vehicle and property damage
- **LAE** (Loss Adjustment Expenses): Investigation and legal costs
- **DED** (Deductible): Amount recovered from policyholder

Each has four components:
- `reserve`: Amount set aside for future payments
- `paid`: Amount already paid out
- `recovered`: Amount recovered (subrogation, deductibles)
- `total_incurred`: `reserve + paid - recovered`

## Metadata File

`metadata.json` contains dataset-level information:

```json
{
  "dataset_name": "lost-and-found-entities-v1",
  "version": "1.0.0",
  "generated_at": "2025-10-18T19:25:00",
  "total_instances": 40,
  "total_claims": 1350,
  "instances": [
    {
      "id": "easy_10_001",
      "difficulty": "easy",
      "num_claims": 10,
      "pages_estimate": 3,
      "problems": ["multi_row"],
      "has_duplicates": false,
      "seed": 42
    }
  ]
}
```

## Evaluation

To evaluate your extraction system:

1. **Extract entities** from each PDF using your method (LLM, OCR+parsing, etc.)
2. **Compare** with ground truth JSON
3. **Calculate metrics**:
   - **Claim-level Recall**: % of claims found
   - **Claim-level Precision**: % of extracted claims that match
   - **Field-level Accuracy**: % of fields extracted correctly
   - **Duplicate Handling**: Correct identification of duplicates
   - **Error Analysis**: Which problems cause failures?

### Example Evaluation Code

```python
import json
from pathlib import Path

def evaluate(predicted: list[dict], ground_truth: list[dict]) -> dict:
    """Compare predicted extractions with ground truth."""
    # Your evaluation logic here
    pass

# Load ground truth
gt = json.loads(Path("easy_10_001.json").read_text())

# Extract from PDF
predicted = your_extraction_system("easy_10_001.pdf")

# Evaluate
metrics = evaluate(predicted, gt)
print(f"Recall: {metrics['recall']:.2%}")
print(f"Precision: {metrics['precision']:.2%}")
```

## Regenerating the Dataset

To regenerate this benchmark (e.g., with different random seed):

```bash
cd benchmarks
python generate_claims_benchmark.py -o claims_new -s 12345
```

See [`generate_claims_benchmark.py`](../generate_claims_benchmark.py) for details.

## Citation

If you use this benchmark in your research, please cite:

```bibtex
@misc{shchoholiev2025lostfound,
  title={Lost-and-Found Entities: A Benchmark for Long-List Entity Extraction},
  author={Shchoholiev, Serhii and Fedoruk, Anton},
  year={2025},
  publisher={Kay.ai}
}
```

## License

See [LICENSE](../../LICENSE) in repository root.

## Contact

- Serhii Shchoholiev - serhii@kay.ai
- Anton Fedoruk - anton@kay.ai
