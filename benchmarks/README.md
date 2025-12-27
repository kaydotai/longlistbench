# Benchmarks

This directory contains benchmark generation and processing tools for the Lost and Found Entities project.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
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
python generate_claims_benchmark.py
```

## OCR Claims PDFs

Process all PDF files in the `claims/` directory using Gemini:

```bash
python ocr_claims_pdfs.py
```

This will:
- Process all PDF files in parallel
- Extract text using Google Gemini vision model
- Save results as `*_ocr.txt` files alongside each PDF
- Skip files that have already been processed
- Handle multi-page PDFs efficiently

The script will show progress for each file and provide a summary at the end.

## Multi-Model Evaluation

Run extraction evaluation across Gemini, GPT-4, and Claude:

```bash
# Full evaluation (all models, all samples)
python evaluate_models.py

# Quick test (one sample per tier)
python evaluate_models.py --quick

# Specific models only
python evaluate_models.py --models gemini gpt4

# Specific tiers/formats
python evaluate_models.py --tiers easy medium --formats detailed
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
