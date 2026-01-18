# Lost and Found Entities

Benchmark for entity extraction from semi-structured insurance claims data with intentionally introduced complexity.

## Quick Start

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
python -m pip install -r benchmarks/requirements.txt
python -m playwright install chromium

# Generate the complete benchmark dataset
python benchmarks/generate_claims_benchmark.py
```

The benchmark will be generated in `benchmarks/claims/` with 4 difficulty tiers (easy, medium, hard, extreme).

See [`benchmarks/README.md`](benchmarks/README.md) for benchmark documentation.

## Benchmark Overview

- **80 benchmark instances** across 4 difficulty tiers × 2 formats
- **2,700 base claims** across all instances (some instances include additional rows due to `large_doc` and `duplicates`)
- **7 problem types** testing real-world complexity (all implemented)
- **2 document formats** (detailed and table views)
- **Ground truth annotations** in JSON format
- **OCR-processed PDFs** simulating production scenarios

### Problem Types

| Code | Meaning |
|------|---------|
| `page_breaks` | A single incident/row is split across PDF pages (content continues on the next page). |
| `multi_row` | Key fields (especially descriptions) span multiple lines/rows instead of being single-line. |
| `duplicates` | Duplicate incidents are inserted (exact repeats) to test deduplication and counting. |
| `large_doc` | Document is much longer than normal (many more incidents/pages). |
| `multiple_tables` | Adds additional irrelevant tables/sections mixed in with the main claims content. |
| `multi_column` | Uses a multi-column layout in parts of the document to stress reading order. |
| `merged_cells` | Uses merged table cells (e.g. `rowspan`/`colspan`) to make table structure harder. |

### Difficulty Tiers

| Tier | Claims/PDF | Instances | Formats | Problems |
|------|------------|-----------|---------|----------|
| Easy | 10 | 15×2 = 30 | Detailed + Table | 1-2 |
| Medium | 25 | 12×2 = 24 | Detailed + Table | 3-4 |
| Hard | 50 | 8×2 = 16 | Detailed + Table | 5-6 |
| Extreme | 100 | 5×2 = 10 | Detailed + Table | All 7 |

### Document Formats

- **Detailed**: Incident sections with line items and financial breakdowns
- **Table**: Compact tabular format with all claims in rows

## Development

For development and testing, see [`benchmarks/synthetic/README.md`](benchmarks/synthetic/README.md) for the synthetic data generator.

## Development Setup

### Installing the Pre-Commit Hook

To ensure the paper compiles successfully before committing, install the pre-commit hook:

```bash
# From the repository root
cp pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

The hook will automatically run `make` in the `paper` directory before each commit and prevent the commit if compilation fails.

**Manually invoking the hook:**
```bash
# Test the hook without committing
.git/hooks/pre-commit
```

**Note:** You can skip the hook for a specific commit using:
```bash
git commit --no-verify
```

### Requirements

- LaTeX distribution (TeX Live, MacTeX, or similar)
- `pdflatex` and `biber` must be available in your PATH