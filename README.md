# LongListBench

Benchmark for long-list entity extraction from semi-structured documents under complex layouts and OCR noise, inspired by recurring patterns observed in real-world claims documents.

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
# This writes JSON, HTML, PDF, and canonical transcript files.
python benchmarks/generate_claims_benchmark.py
```

## Reproducibility

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
- **7 implemented problem types** approximating common long-list failure modes
- **2 document formats** (detailed and table views)
- **Ground truth annotations** in JSON format
- **Canonical transcripts** derived from rendered HTML
- **OCR transcripts** derived from page-image OCR

### Problem Types

| Code | Meaning |
|------|---------|
| `page_breaks` | Detailed documents can split one incident across pages; table documents insert row-boundary page breaks with repeated table headers. |
| `multi_row` | Key fields (especially descriptions) span multiple lines/rows instead of being single-line. |
| `duplicates` | Duplicate incidents are inserted (exact repeats) to test deduplication and counting. |
| `large_doc` | Document is much longer than normal (many more incidents/pages). |
| `multiple_tables` | Adds additional irrelevant tables/sections mixed in with the main claims content. |
| `multi_column` | Uses a multi-column layout in detailed-format content and distractor sections to stress reading order. |
| `merged_cells` | Uses merged table cells (e.g. `rowspan`/`colspan`) to make table structure harder. |

The strongest `page_breaks` and `multi_column` effects are format-dependent: detailed documents receive split-record page breaks and multi-column primary content, while table documents keep the main claims table single-span.

### Difficulty Tiers

| Tier | Seed Claims/PDF | Released Rows/Doc | Instances | Formats | Problems |
|------|-----------------|-------------------|-----------|---------|----------|
| Easy | 10 | 10-11 | 15×2 = 30 | Detailed + Table | 1-2 |
| Medium | 25 | 25-27 | 12×2 = 24 | Detailed + Table | 3-4 |
| Hard | 50 | 55 | 8×2 = 16 | Detailed + Table | 5-6 |
| Extreme | 100 | 500 | 5×2 = 10 | Detailed + Table | All 7 |

The released dataset includes additional rows from `duplicates` and `large_doc`. Extreme filenames retain a legacy `_100_` seed-count suffix, but every released extreme document contains 500 incidents.

### Document Formats

- **Detailed**: Incident sections with line items and financial breakdowns
- **Table**: Compact tabular format with all claims in rows

## Verified Gemini 2.5 OCR Baseline

Using the synchronized OCR-condition snapshot from this repository, we highlight two local extraction regimes:

| Regime | Overall weighted micro F1 | Extreme-tier weighted micro F1 |
|--------|----------------------------|--------------------------------|
| Full-context one-shot | 27.4% | 5.9% |
| Auto-chunked (`longlistbench`) | 84.8% | 81.7% |

Moving from full-context one-shot to the local auto-chunked regime improves overall weighted F1 by 57.4 points and extreme-tier weighted F1 by 75.8 points on the same snapshot. The one-shot regime remains strong on easy documents (97.2%), but drops to 74.6% on medium, 44.4% on hard, and 5.9% on extreme. By contrast, the local auto-chunked regime reaches 97.3% weighted F1 on easy, 96.5% on medium, 87.7% on hard, 71.0% on detailed documents overall, and 95.9% on table documents overall. Chunking therefore mitigates the catastrophic long-context failure mode, but the local chunked baseline still leaves substantial residual errors, especially on long detailed documents. The evaluator now also supports direct clean-vs-OCR comparisons by running the same extractor over `canonical` and `ocr` transcript conditions.

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
