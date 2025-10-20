#!/usr/bin/env python3
"""
Test OCR on a few example PDFs to verify the output quality.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path to import from ocr_claims_pdfs
sys.path.insert(0, str(Path(__file__).parent))

from ocr_claims_pdfs import setup_gemini, process_pdf

def main():
    # Setup paths
    script_dir = Path(__file__).parent
    claims_dir = script_dir / "claims"
    
    # Select samples from each tier to test all problems
    test_files = [
        # Easy: 1-2 problems (already tested)
        # "easy_10_001_detailed.pdf",
        # "easy_10_001_table.pdf",
        # Medium: 3-4 problems (already tested)
        # "medium_25_001_detailed.pdf",
        # "medium_25_001_table.pdf",
        # Hard: 5-6 problems - test these
        "hard_50_001_detailed.pdf",
        "hard_50_001_table.pdf",
        # Extreme: all 7 problems - test one sample
        "extreme_100_001_detailed.pdf",
    ]
    
    print("Testing OCR on sample PDFs...")
    print()
    
    # Setup Gemini
    print("Setting up Gemini API...")
    model = setup_gemini()
    print("✓ Gemini API configured")
    print()
    
    # Process test files
    for filename in test_files:
        pdf_path = claims_dir / filename
        
        if not pdf_path.exists():
            print(f"⚠ Warning: {filename} not found, skipping")
            continue
        
        output_path = pdf_path.parent / f"{pdf_path.stem}_ocr.md"
        
        print(f"Processing {filename}...")
        # Use only 1 worker to avoid rate limits
        success = process_pdf(model, pdf_path, output_path, max_workers=1)
        
        if success:
            print(f"  ✓ Saved to: {output_path.name}")
            print(f"  Review the output at: {output_path}")
        else:
            print(f"  ✗ Failed to process")
        
        print()
    
    print("="*60)
    print("Test complete! Review the output files to verify quality.")
    print("If satisfied, run ocr_claims_pdfs.py to process all files.")


if __name__ == "__main__":
    main()
