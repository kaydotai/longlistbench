# Synthetic Insurance Claims Benchmark

This benchmark tests entity extraction from semi-structured insurance claims data with intentionally introduced problems.

## Workflow

```
1. Generate Structured Data (JSON/CSV)  ← Golden data for comparison
          ↓
2. Generate HTML with Problems          ← Inject complexity/issues
          ↓
3. Render HTML → PDF                    ← Final test document
          ↓
4. OCR PDF → Text                       ← Convert document to machine-readable text
          ↓
5. Extract Entities from Text           ← Test your extraction system
          ↓
6. Compare with Golden Data             ← Evaluate accuracy
```

## Problems Injected

The benchmark introduces real-world document complexity issues:

1. **Rows split across pages** - Table rows broken by page breaks
2. **Multi-row entities** - Cells containing line breaks (addresses, descriptions)
3. **Exact duplicates** - Duplicate claim records in the document
4. **Large documents** - 500+ claim records to test scalability
5. **Multiple tables** - Relevant claims + irrelevant content (company directory, etc.)
6. **Multi-column layout** - Research paper style with 2-column formatting
7. **Merged cells** - Cells spanning multiple columns/rows

## Setup

```bash
# From the repository root
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
python -m pip install -r benchmarks/requirements.txt

# Install Playwright browsers (for PDF rendering)
python -m playwright install chromium
```

## Usage

The commands below assume you are running from `benchmarks/synthetic/`.

### 1. Generate Structured Data (Golden Truth)

```bash
# Generate 100 claims
python generate_claim_data.py -n 100 -o data/claims_100.json

# Generate with custom seed for reproducibility
python generate_claim_data.py -n 1000 -s 12345 -o data/claims_1000.json

# Generate CSV instead of JSON
python generate_claim_data.py -n 50 --csv -o data/claims_50.csv
```

### 2. Generate HTML with Problems

```bash
# Generate HTML with all problems enabled
python generate_html.py \
    -i data/claims_100.json \
    -o data/claims_100.html \
    --all-problems

# Generate with specific problems only
python generate_html.py \
    -i data/claims_100.json \
    -o data/claims_100_simple.html \
    --page-breaks \
    --multi-row \
    --duplicates

# Available problem flags:
# --page-breaks      Rows split across pages
# --multi-row        Multi-row entities
# --duplicates       Add exact duplicates
# --large-doc        Generate 500+ claims
# --multiple-tables  Add irrelevant tables
# --multi-column     Use 2-column layout
# --merged-cells     Use merged cells
# --all-problems     Enable everything
```

### 3. Render HTML to PDF

```bash
# Convert HTML to PDF
python html_to_pdf.py -i data/claims_100.html -o data/claims_100.pdf

# Output path is optional (defaults to same name with .pdf)
python html_to_pdf.py -i data/claims_100.html
```

### Complete Pipeline Example

```bash
# Generate different complexity levels

# Easy: 50 claims, minimal problems
python generate_claim_data.py -n 50 -o data/easy_claims.json
python generate_html.py -i data/easy_claims.json -o data/easy_claims.html --multi-row
python html_to_pdf.py -i data/easy_claims.html

# Medium: 100 claims, some problems
python generate_claim_data.py -n 100 -o data/medium_claims.json
python generate_html.py -i data/medium_claims.json -o data/medium_claims.html \
    --page-breaks --multi-row --duplicates --multiple-tables

# Hard: 500+ claims, all problems
python generate_claim_data.py -n 200 -o data/hard_claims.json
python generate_html.py -i data/hard_claims.json -o data/hard_claims.html \
    --all-problems
python html_to_pdf.py -i data/hard_claims.html
```

## Entity Schema

Generated incidents conform to `LossRunIncident` (see `benchmarks/models/loss_run.py`). The schema includes incident identifiers, policy metadata, narrative fields, and nested financial breakdowns.

Key fields:

- `incident_number`, `reference_number`
- `company_name`, `division`, `insured`, `agency`, `policy_number`, `policy_state`
- `coverage_type`, `status`, `date_of_loss`, `date_reported`, `loss_state`, `unit_number`, `driver_name`, `claimants`, `cause_code`, `handler`, `adjuster_notes`, `description`
- `bi`, `pd`, `lae`, `ded` (each has `reserve`, `paid`, `recovered`, `total_incurred`)

## File Structure

```
benchmarks/synthetic/
├── README.md                    # This file
├── generate_claim_data.py       # Step 1: Generate golden data
├── generate_html.py             # Step 2: Generate HTML with problems
├── html_to_pdf.py               # Step 3: Render to PDF
├── data/                        # Output directory
│   ├── *.json                   # Golden data (structured)
│   ├── *.html                   # HTML with problems
│   └── *.pdf                    # Final test documents
└── templates/                   # (Future: HTML templates)
```

## Evaluation

To evaluate your extraction system:

1. Extract entities from the generated PDF
2. Compare extracted entities with the golden JSON data
3. Measure:
   - **Recall**: How many entities were found?
   - **Precision**: How many extracted entities are correct?
   - **Field accuracy**: Are all fields extracted correctly?
   - **Duplicate handling**: Are exact duplicates properly identified?

## Notes

- All generators use seeded randomness for reproducibility
- The golden JSON/CSV should be used as ground truth for comparison
- PDF rendering requires a Chromium browser (installed via Playwright)
- Generated documents are designed to test extraction robustness, not readability
