# Benchmarks

This directory contains benchmark generation and processing tools for the Lost and Found Entities project.

## Setup

Run these commands from the repository root.

1. Install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r benchmarks/requirements.txt
   python -m playwright install chromium
   ```

2. Install poppler (required for PDF processing):
   ```bash
   # macOS
   brew install poppler
   
   # Linux
   apt-get install poppler-utils
   ```

3. Set up API keys in `.env`:
   ```
   GEMINI_API_KEY=your-gemini-api-key
   OPENAI_API_KEY=your-openai-api-key
   ANTHROPIC_API_KEY=your-anthropic-api-key
   ```

## Generate Claims Benchmark

Generate synthetic insurance claim PDFs:

```bash
python benchmarks/generate_claims_benchmark.py
```

If you need to regenerate `claims/metadata.json` (without regenerating PDFs/HTML/JSON), run:

```bash
python benchmarks/generate_claims_benchmark.py --rebuild-metadata
```

## Problem Matrix (Which files have which problems)

The authoritative mapping of `instance_id -> problems` lives in the generated `<output_dir>/metadata.json` under `instances[]`.

Each instance is generated in **two formats** (`detailed` and `table`) and each format produces:

- **PDF**: `<instance_id>.pdf`
- **HTML**: `<instance_id>.html`
- **Ground truth**: `<instance_id>.json`

Below is the expected problem mapping based on `BENCHMARK_CONFIG` (the instance number cycles through the tier’s problem combinations).

### Easy (`easy_10_XXX_{detailed,table}`)

| Instance numbers | Enabled problems |
|---|---|
| `001, 006, 011` | `multi_row` |
| `002, 007, 012` | `page_breaks` |
| `003, 008, 013` | `multi_row`, `page_breaks` |
| `004, 009, 014` | `duplicates` |
| `005, 010, 015` | `multi_row`, `duplicates` |

### Medium (`medium_25_XXX_{detailed,table}`)

| Instance numbers | Enabled problems |
|---|---|
| `001, 005, 009` | `page_breaks`, `multi_row`, `duplicates` |
| `002, 006, 010` | `page_breaks`, `multi_row`, `multiple_tables` |
| `003, 007, 011` | `multi_row`, `duplicates`, `multiple_tables` |
| `004, 008, 012` | `page_breaks`, `duplicates`, `multiple_tables` |

### Hard (`hard_50_XXX_{detailed,table}`)

| Instance numbers | Enabled problems |
|---|---|
| `001, 004, 007` | `page_breaks`, `multi_row`, `duplicates`, `multiple_tables`, `multi_column` |
| `002, 005, 008` | `page_breaks`, `multi_row`, `duplicates`, `multiple_tables`, `merged_cells` |
| `003, 006` | `page_breaks`, `multi_row`, `duplicates`, `multi_column`, `merged_cells` |

### Extreme (`extreme_100_XXX_{detailed,table}`)

| Instance numbers | Enabled problems |
|---|---|
| `001-005` | `page_breaks`, `multi_row`, `duplicates`, `large_doc`, `multiple_tables`, `multi_column`, `merged_cells` |

## OCR Claims PDFs

Process all PDF files in the `claims/` directory using Gemini:

```bash
python benchmarks/ocr_claims_pdfs.py
```

This will:
- Process all PDF files in parallel
- Extract text using Google Gemini vision model
- Save results as `*_ocr.md` files alongside each PDF
- Skip files that have already been processed
- Handle multi-page PDFs efficiently

The script will show progress for each file and provide a summary at the end.

## Multi-Model Evaluation

Run extraction evaluation across Gemini, GPT-4, and Claude:

```bash
# Full evaluation (all models, all samples)
python benchmarks/evaluate_models.py

# Quick test (one sample per tier)
python benchmarks/evaluate_models.py --quick

# Specific models only
python benchmarks/evaluate_models.py --models gemini gpt4

# Specific tiers/formats
python benchmarks/evaluate_models.py --tiers easy medium --formats detailed
```

Results are saved to `results/`:
- `evaluation_report.json` - Full metrics data
- `evaluation_report.md` - Human-readable summary

## Directory Structure

- `claims/` - Generated benchmark claims (PDFs, JSONs, and OCR results)
- `results/` - Evaluation results and reports
- `synthetic/` - Synthetic data generation tools
- `generate_claims_benchmark.py` - Main benchmark generation script
- `ocr_claims_pdfs.py` - OCR processing script for PDFs
- `evaluate_models.py` - Multi-model evaluation script
