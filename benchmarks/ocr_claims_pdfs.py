#!/usr/bin/env python3
"""
OCR all PDF files in the claims benchmark directory using Google Gemini.
Saves OCR results as Markdown files alongside the PDFs.
"""

import asyncio
import io
import os
import sys
from pathlib import Path

try:
    from google import genai
    from google.genai import types
    from PIL import Image
    import pdf2image
    from pdf2image import pdfinfo_from_path
    from dotenv import load_dotenv
    from tenacity import (
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
        wait_fixed,
    )
except ImportError as e:
    print(f"Error: Required packages not installed: {e}")
    print("Please install them with:")
    print("  pip install google-genai tenacity pillow pdf2image python-dotenv")
    print("\nYou may also need to install poppler:")
    print("  macOS: brew install poppler")
    print("  Linux: apt-get install poppler-utils")
    sys.exit(1)

# Load environment variables from .env file
load_dotenv()

# Try to import Google API error for retry handling
try:
    from google.genai.errors import APIError as GoogleApiError
except ImportError:
    GoogleApiError = None

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


# Build retriable exceptions tuple
_RETRIABLE_EXCEPTIONS = (Exception,)  # Base case
if GoogleApiError is not None:
    _RETRIABLE_EXCEPTIONS = (GoogleApiError,)


def log_retry(retry_state):
    """Log retry attempts."""
    exc = retry_state.outcome.exception()
    print(f"    [retry] Attempt {retry_state.attempt_number} failed: {type(exc).__name__}: {exc}")


# Retry decorator for general API errors with exponential backoff
retry_on_gemini_call = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=4, min=5, max=120),
    retry=retry_if_exception_type(_RETRIABLE_EXCEPTIONS),
    after=log_retry,
)

# Retry decorator specifically for rate limits with fixed wait
retry_on_rate_limit = retry(
    stop=stop_after_attempt(10),
    wait=wait_fixed(60),
    retry=retry_if_exception_type(_RETRIABLE_EXCEPTIONS),
    after=log_retry,
)


def setup_gemini():
    """Configure Gemini API client with API key from environment variable."""
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key or api_key == 'your-api-key-here':
        print("Error: GEMINI_API_KEY not set.")
        print("Please set GEMINI_API_KEY environment variable")
        sys.exit(1)
    
    return genai.Client(api_key=api_key)


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


@retry_on_gemini_call
@retry_on_rate_limit
async def ocr_image_async(client: genai.Client, image: Image.Image) -> str:
    """OCR a single image using Gemini async API with retries."""
    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        contents=[
            image,
            "OCR the image into Markdown. Format tables as CSV. Do not surround your output with triple backticks.",
        ],
    )
    return response.text or ""


async def ocr_page_with_gemini(client: genai.Client, image: Image.Image, page_num: int) -> str:
    """Send a single image to Gemini for OCR and return Markdown text."""
    try:
        page_text = await ocr_image_async(client, image)
        return f"# Page {page_num}\n\n{page_text}\n\n"
    except Exception as e:
        print(f"Warning: Page {page_num} failed after all retries: {e}")
        return f"# Page {page_num}\n\n[Error: {e}]\n\n"


async def process_page_async(client: genai.Client, pdf_path: Path, page_num: int, semaphore: asyncio.Semaphore) -> tuple[int, str]:
    """Process a single page with semaphore for concurrency control."""
    async with semaphore:
        image = convert_pdf_page(pdf_path, page_num)
        if image is None:
            return (page_num, f"# Page {page_num}\n\n[Error: Could not convert page]\n\n")
        
        page_text = await ocr_page_with_gemini(client, image, page_num)
        return (page_num, page_text)


async def process_pdf_async(client: genai.Client, pdf_path: Path, output_path: Path, max_concurrent: int = 3) -> bool:
    """Process PDF pages with async concurrency control."""
    total_pages = get_page_count(pdf_path)
    if total_pages is None:
        return False
    
    print(f"  Pages: {total_pages}")
    
    # Use semaphore to limit concurrent API calls
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Create tasks for all pages
    tasks = [
        process_page_async(client, pdf_path, page_num, semaphore)
        for page_num in range(1, total_pages + 1)
    ]
    
    # Run all tasks concurrently (limited by semaphore)
    results = await asyncio.gather(*tasks)
    
    # Sort results by page number and write
    results_dict = {page_num: text for page_num, text in results}
    with open(output_path, 'w', encoding='utf-8') as f:
        for page_num in sorted(results_dict.keys()):
            f.write(results_dict[page_num])
    
    return True


def process_pdf(client: genai.Client, pdf_path: Path, output_path: Path, max_concurrent: int = 3) -> bool:
    """Synchronous wrapper for async PDF processing."""
    return asyncio.run(process_pdf_async(client, pdf_path, output_path, max_concurrent))


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
    client = setup_gemini()
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
        
        success = process_pdf(client, pdf_path, output_path, max_concurrent=3)
        
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
    print(f"\nRun validate_ocr_vs_golden.py to check coverage.")


if __name__ == "__main__":
    main()
