"""Convert HTML files to PDF using playwright (chromium)."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


async def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    """Render HTML file to PDF using Playwright's chromium browser.
    
    Args:
        html_path: Path to input HTML file
        pdf_path: Path to output PDF file
    """
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Load HTML file
        html_content = html_path.read_text(encoding="utf-8")
        await page.set_content(html_content)

        await page.emulate_media(media="print")

        # Generate PDF with proper print settings
        await page.pdf(
            path=str(pdf_path),
            format="A4",
            landscape=True,
            prefer_css_page_size=True,
            print_background=True,
            margin={
                "top": "2cm",
                "right": "2cm",
                "bottom": "2cm",
                "left": "2cm",
            },
        )

        await browser.close()

    print(f"✓ Rendered PDF → {pdf_path}")


async def main_async() -> None:
    parser = argparse.ArgumentParser(
        description="Convert HTML to PDF using Playwright."
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Input HTML file path",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output PDF file path (default: same name as input with .pdf)",
    )

    args = parser.parse_args()

    html_path = Path(args.input)
    pdf_path = (
        Path(args.output)
        if args.output
        else html_path.with_suffix(".pdf")
    )

    await html_to_pdf(html_path, pdf_path)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
