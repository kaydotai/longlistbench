# LongListBench

Benchmark for long-list entity extraction from semi-structured documents under layout and OCR noise, inspired by recurring patterns observed in real-world claims documents.

This benchmark was developed at [Kay.ai](https://kay.ai).

## Quick Start

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
python -m pip install -r benchmarks/requirements.txt
python -m playwright install chromium

# Set API keys (only needed for OCR/evaluation runs)
cp .env.example .env

# Generate the complete benchmark dataset
python benchmarks/generate_claims_benchmark.py
```

## Command-Line Reproducibility

Convenience targets are provided via the repository root `Makefile`:

```bash
make help

# Create venv + install deps + install Playwright Chromium
make setup

# Generate synthetic benchmark dataset (PDF/HTML/JSON)
make generate

# Build the paper
make paper
```

See [`benchmarks/README.md`](benchmarks/README.md) for benchmark documentation.

## Versioning and Citation

- **Version**: see `VERSION`.
- **Citation metadata**: see `CITATION.cff`.

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

Note: these are nominal sizes; the released dataset includes additional rows from `duplicates` and `large_doc`. In the current release, ground-truth incident counts per document range from 10--11 (easy), 25--27 (medium), 55 (hard), and 500 (extreme).

### Document Formats

- **Detailed**: Incident sections with line items and financial breakdowns
- **Table**: Compact tabular format with all claims in rows

## Baseline Results (Released)

Schema-conformant field-level micro F1 averaged across all 80 documents (see `benchmarks/results_*_all/evaluation_report.json`):

| Model | Avg F1 | Avg Recall | Avg Precision |
|------|--------|------------|---------------|
| Gemini 2.5 | 81.9% | 80.4% | 83.4% |
| GPT-4o | 80.0% | 78.3% | 82.0% |
| GPT-5.2 | 78.1% | 76.8% | 79.6% |

## Development

For development and testing, see [`benchmarks/synthetic/README.md`](benchmarks/synthetic/README.md) for the synthetic data generator.

## Development Setup

### Installing the Pre-Commit Hook

Optional: install a pre-commit hook to quickly sanity-check that the paper compiles:

```bash
# From the repository root
cp pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

The hook runs a fast LaTeX compile (`make quick`) in the `paper` directory; in strict mode it can prevent the commit if compilation fails.

By default, the hook is best-effort and will skip (or warn) when dependencies are missing. To make paper compilation failures block commits, set:

```bash
export STRICT_PAPER_COMPILE=1
```

**Manually invoking the hook:**
```bash
# Test the hook without committing
.git/hooks/pre-commit
```

Alternatively, run the same check from your virtualenv:
```bash
source .venv/bin/activate
make -C paper quick
```

**Note:** You can skip the hook for a specific commit using:
```bash
git commit --no-verify
```

### Requirements

- LaTeX distribution (TeX Live, MacTeX, or similar)
- `pdflatex` and `biber` must be available in your PATH