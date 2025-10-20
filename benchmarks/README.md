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

3. Set up your Gemini API key in `.env`:
   ```
   GEMINI_API_KEY=your-actual-api-key-here
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

## Directory Structure

- `claims/` - Generated benchmark claims (PDFs, JSONs, and OCR results)
- `synthetic/` - Synthetic data generation tools
- `generate_claims_benchmark.py` - Main benchmark generation script
- `ocr_claims_pdfs.py` - OCR processing script for PDFs
