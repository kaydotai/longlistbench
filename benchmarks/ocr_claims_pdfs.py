#!/usr/bin/env python3
"""
OCR all PDF files in the claims benchmark directory using Google Gemini.
Saves OCR results as Markdown files alongside the PDFs.
"""

import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import google.generativeai as genai
    from PIL import Image
    import pdf2image
    from pdf2image import pdfinfo_from_path
    from dotenv import load_dotenv
except ImportError:
    print("Error: Required packages not installed.")
    print("Please install them with:")
    print("  pip install -r requirements.txt")
    print("\nYou may also need to install poppler:")
    print("  macOS: brew install poppler")
    print("  Linux: apt-get install poppler-utils")
    sys.exit(1)

# Load environment variables from .env file
load_dotenv()

SYSTEM_PROMPT = """
You are a document conversion assistant specialized in converting images into structured text while preserving layout and form elements. Follow these specific instructions:

- Maintain original spacing, alignment, and indentation
- Keep tables and multi-column layouts using spaces/tabs
- Preserve field labels with their delimiters (:)
- Show checkboxes as [X] checked, [ ] unchecked
- Show radio buttons as (•) selected, ( ) unselected
- Keep address blocks and phone numbers in original format
- Preserve special characters ($, %, etc.) exactly as shown
- Render signatures as [Signature] or actual text if present
- Maintain section headers and sub-headers
- Keep page numbers and document identifiers
- Preserve form numbering and copyright text
- Keep line breaks and paragraph spacing as shown

Remember: Convert ONLY what is visible in the document - do not add, assume, or manufacture any information that isn't explicitly shown in the source image.
"""


def setup_gemini():
    """Configure Gemini API with API key from environment variable."""
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key or api_key == 'your-api-key-here':
        print("Error: GEMINI_API_KEY not set in .env file.")
        print("Please set GEMINI_API_KEY in the .env file")
        sys.exit(1)
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name='gemini-2.0-flash-exp',
        system_instruction=SYSTEM_PROMPT
    )


def get_page_count(pdf_path):
    """Get the number of pages in the PDF."""
    try:
        info = pdfinfo_from_path(pdf_path)
        return info['Pages']
    except Exception as e:
        print(f"Error getting page count for {pdf_path}: {e}")
        return None


def convert_pdf_page(pdf_path, page_num):
    """Convert a single page of PDF to PIL Image."""
    try:
        # pdf2image uses 1-based page numbering
        images = pdf2image.convert_from_path(
            pdf_path,
            first_page=page_num,
            last_page=page_num
        )
        return images[0] if images else None
    except Exception as e:
        print(f"Error converting page {page_num} of {pdf_path.name}: {e}")
        return None


def ocr_page_with_gemini(model, image, page_num):
    """Send a single image to Gemini for OCR and return Markdown text."""
    import time
    prompt = "OCR the image into Markdown. Format tables as CSV. Do not surround your output with triple backticks."
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content([image, prompt])
            page_text = response.text
            return f"# Page {page_num}\n\n{page_text}\n\n"
        except Exception as e:
            error_str = str(e)
            if '429' in error_str or 'quota' in error_str.lower():
                if attempt < max_retries - 1:
                    wait_time = 10 * (attempt + 1)  # 10s, 20s, 30s
                    print(f"    Rate limit hit on page {page_num}, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
            print(f"Warning: Error processing page {page_num}: {e}")
            return f"# Page {page_num}\n\n[Error processing this page: {e}]\n\n"
    
    return f"# Page {page_num}\n\n[Error: Max retries exceeded]\n\n"


def process_single_page(model, pdf_path, page_num, total_pages):
    """Process a single page (convert + OCR). Returns (page_num, page_text)."""
    # Convert single page
    image = convert_pdf_page(pdf_path, page_num)
    if image is None:
        page_text = f"# Page {page_num}\n\n[Error: Could not convert page]\n\n"
    else:
        page_text = ocr_page_with_gemini(model, image, page_num)
    
    return (page_num, page_text)


def process_pdf(model, pdf_path, output_path, max_workers=5):
    """Process PDF pages in parallel using ThreadPoolExecutor."""
    # Get total page count
    total_pages = get_page_count(pdf_path)
    if total_pages is None:
        return False
    
    print(f"  Pages: {total_pages}")
    
    # Clear/create output file
    output_path.write_text("", encoding='utf-8')
    
    # Process pages in parallel
    results = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all pages
        futures = {
            executor.submit(process_single_page, model, pdf_path, page_num, total_pages): page_num
            for page_num in range(1, total_pages + 1)
        }
        
        # Collect results as they complete
        for future in as_completed(futures):
            page_num, page_text = future.result()
            results[page_num] = page_text
    
    # Write results in order
    with open(output_path, 'w', encoding='utf-8') as f:
        for page_num in sorted(results.keys()):
            f.write(results[page_num])
    
    return True


def main():
    # Setup paths
    script_dir = Path(__file__).parent
    claims_dir = script_dir / "claims"
    
    if not claims_dir.exists():
        print(f"Error: Claims directory not found: {claims_dir}")
        sys.exit(1)
    
    # Find all PDF files
    pdf_files = sorted(claims_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"No PDF files found in {claims_dir}")
        sys.exit(1)
    
    print(f"Found {len(pdf_files)} PDF files to process")
    print()
    
    # Setup Gemini
    print("Setting up Gemini API...")
    model = setup_gemini()
    print("✓ Gemini API configured")
    print()
    
    # Process each PDF
    success_count = 0
    fail_count = 0
    
    for i, pdf_path in enumerate(pdf_files, 1):
        output_path = pdf_path.parent / f"{pdf_path.stem}_ocr.md"
        
        # Skip if already processed
        if output_path.exists():
            print(f"[{i}/{len(pdf_files)}] Skipping {pdf_path.name} (already processed)")
            success_count += 1
            continue
        
        print(f"[{i}/{len(pdf_files)}] Processing {pdf_path.name}")
        
        success = process_pdf(model, pdf_path, output_path)
        
        if success:
            print(f"  ✓ Saved to: {output_path.name}")
            success_count += 1
        else:
            print(f"  ✗ Failed to process")
            fail_count += 1
        
        print()
    
    # Summary
    print("="*60)
    print(f"Processing complete!")
    print(f"  Success: {success_count}/{len(pdf_files)}")
    print(f"  Failed:  {fail_count}/{len(pdf_files)}")


if __name__ == "__main__":
    main()
