# Benchmark Testing Guide

This guide explains how to test extraction approaches on the Lost-and-Found Entities benchmark.

## Setup Complete

1. ✅ OCR processing with Gemini (markdown output with CSV tables)
2. ✅ Ground truth JSON files for evaluation
3. ✅ Test extraction scripts

## 7 Problem Types in Benchmark

1. **Page Breaks** - Table rows split across page boundaries
2. **Multi-row Entities** - Cells with line breaks (addresses, descriptions)
3. **Exact Duplicates** - Identical claim records appearing multiple times
4. **Large Documents** - High volume of records (100+ claims)
5. **Multiple Tables** - Relevant claims mixed with irrelevant content
6. **Multi-column Layout** - Research paper style formatting
7. **Merged Cells** - Cells spanning multiple columns/rows (table format)

## Testing Scripts

### 1. Analyze Problems (`analyze_problems.py`)

Shows which problems are present in each benchmark instance:

```bash
python benchmarks/analyze_problems.py
```

### 2. Test Extraction (`test_extraction.py`)

Tests simple zero-shot LLM extraction on OCR'd samples:

```bash
python benchmarks/test_extraction.py
```

This script:
- Loads OCR'd markdown files
- Uses simple prompt to extract claims
- Compares against ground truth
- Reports recall, precision, F1 scores
- Identifies missing/extra claims

### 3. OCR Samples

Test with a few samples first:

```bash
python benchmarks/test_ocr.py
```

Process all PDFs:

```bash
python benchmarks/ocr_claims_pdfs.py
```

## Expected Failure Modes

Based on the 7 problems, here's what we expect to see:

### Problem 1: Page Breaks
- **Symptom**: Claims split across pages are missed or counted twice
- **Why**: LLM loses context when row continues on next page
- **Fix**: Better page boundary handling, accumulative generation

### Problem 2: Multi-row Entities
- **Symptom**: Addresses/descriptions with line breaks cause field misalignment
- **Why**: OCR may insert extra newlines, confusing structure
- **Fix**: Better structure detection, robust parsing

### Problem 3: Duplicates
- **Symptom**: Same claim extracted multiple times or missed entirely
- **Why**: Need to detect intentional duplicates vs. OCR errors
- **Fix**: Deduplication logic with fuzzy matching

### Problem 4: Large Documents
- **Symptom**: Low recall on 100+ claim documents
- **Why**: Context window limits, model attention degradation
- **Fix**: Chunking strategies, accumulative extraction

### Problem 5: Multiple Tables
- **Symptom**: Irrelevant data extracted as claims
- **Why**: Must distinguish claims table from other tables
- **Fix**: Table classification, better filtering

### Problem 6: Multi-column Layout
- **Symptom**: Text order scrambled, fields misaligned
- **Why**: OCR reading order may not follow logical flow
- **Fix**: Layout analysis before extraction

### Problem 7: Merged Cells
- **Symptom**: Values from merged cells duplicated or lost
- **Why**: CSV format doesn't preserve cell merging info
- **Fix**: Better table structure preservation in OCR

## Evaluation Metrics

- **Recall**: What % of claims did we find?
- **Precision**: What % of extracted claims are correct?
- **F1**: Harmonic mean of precision and recall
- **Field Accuracy**: How accurate are individual fields?
- **Duplicate Handling**: Can we correctly identify true duplicates?

## Next Steps

1. Run extraction test on current OCR samples
2. Identify which problems cause biggest failures
3. Test improved extraction strategies:
   - Chunking for large documents
   - Accumulative generation
   - Better prompting
   - Structure-aware parsing
4. Expand to full benchmark (all 80 instances)

## Files

- `test_extraction.py` - Simple extraction test with zero-shot prompting
- `analyze_problems.py` - Problem type analysis
- `test_ocr.py` - OCR test on samples
- `ocr_claims_pdfs.py` - Batch OCR all PDFs
- `TESTING.md` - This file
