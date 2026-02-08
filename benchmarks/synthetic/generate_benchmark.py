#!/usr/bin/env python3
"""Complete pipeline: Generate claims → HTML → PDF for benchmarking.

This script runs the full benchmark generation pipeline in one command.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

# Import from local modules
from generate_claim_data import generate_incidents
from generate_html import LossRunHTMLGenerator
from html_to_pdf import html_to_pdf


async def generate_benchmark_async(
    num_claims: int,
    output_prefix: str,
    problems: dict[str, bool],
    seed: int = 42,
) -> None:
    """Run complete benchmark generation pipeline.
    
    Args:
        num_claims: Number of incidents to generate
        output_prefix: Prefix for output files (e.g., 'data/hard')
        problems: Dictionary of problem flags
        seed: Random seed for reproducibility
    """
    base_path = Path(output_prefix)
    base_path.parent.mkdir(parents=True, exist_ok=True)

    json_path = base_path.with_suffix(".json")
    html_path = base_path.with_suffix(".html")
    pdf_path = base_path.with_suffix(".pdf")

    # Step 1: Generate structured incidents data
    print(f"\n[1/3] Generating {num_claims} incidents...")
    incidents = generate_incidents(num_claims, seed=seed, start_year=2023)
    generator = LossRunHTMLGenerator(seed=seed)
    incidents_dicts = [i.model_dump() for i in incidents]
    incidents_dicts = generator.apply_document_problems(incidents_dicts, problems)
    json_path.write_text(json.dumps(incidents_dicts, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✓ Saved {len(incidents_dicts)} incidents → {json_path}")

    # Step 2: Generate HTML with problems
    print("\n[2/3] Generating HTML with problems...")
    html_content = generator.generate(incidents_dicts, problems=problems)
    html_path.write_text(html_content, encoding="utf-8")
    
    enabled_problems = [k for k, v in problems.items() if v]
    print(f"✓ Generated HTML → {html_path}")
    print(f"  Problems enabled: {', '.join(enabled_problems) if enabled_problems else 'none'}")

    # Step 3: Render PDF
    print("\n[3/3] Rendering PDF...")
    await html_to_pdf(html_path, pdf_path)

    print(f"\n{'='*60}")
    print("✓ Benchmark generation complete!")
    print(f"{'='*60}")
    print(f"  Golden data: {json_path}")
    print(f"  HTML:        {html_path}")
    print(f"  PDF:         {pdf_path}")
    print(f"  Claims:      {len(incidents_dicts)}")
    print(f"  Problems:    {', '.join(enabled_problems) if enabled_problems else 'none'}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Complete benchmark generation pipeline: JSON → HTML → PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Easy benchmark (50 claims, minimal problems)
  python generate_benchmark.py -n 50 -o data/easy --multi-row

  # Medium benchmark (100 claims, some problems)
  python generate_benchmark.py -n 100 -o data/medium --page-breaks --multi-row --duplicates

  # Hard benchmark (all problems)
  python generate_benchmark.py -n 200 -o data/hard --all-problems
        """,
    )

    parser.add_argument(
        "-n",
        "--num-claims",
        type=int,
        default=100,
        help="Number of claims to generate (default: 100)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output path prefix (e.g., 'data/benchmark_hard')",
    )
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )

    # Problem flags
    parser.add_argument(
        "--page-breaks",
        action="store_true",
        help="Problem 1: Split rows across pages",
    )
    parser.add_argument(
        "--multi-row",
        action="store_true",
        help="Problem 2: Multi-row entities",
    )
    parser.add_argument(
        "--duplicates",
        action="store_true",
        help="Problem 3: Add exact duplicates",
    )
    parser.add_argument(
        "--large-doc",
        action="store_true",
        help="Problem 4: Generate large document (500+ claims)",
    )
    parser.add_argument(
        "--multiple-tables",
        action="store_true",
        help="Problem 5: Add irrelevant tables",
    )
    parser.add_argument(
        "--multi-column",
        action="store_true",
        help="Problem 6: Use multi-column layout",
    )
    parser.add_argument(
        "--merged-cells",
        action="store_true",
        help="Problem 7: Use merged cells",
    )
    parser.add_argument(
        "--all-problems",
        action="store_true",
        help="Enable all problems",
    )

    args = parser.parse_args()

    # Build problem configuration
    problems = {
        "page_breaks": args.all_problems or args.page_breaks,
        "multi_row": args.all_problems or args.multi_row,
        "duplicates": args.all_problems or args.duplicates,
        "large_doc": args.all_problems or args.large_doc,
        "multiple_tables": args.all_problems or args.multiple_tables,
        "multi_column": args.all_problems or args.multi_column,
        "merged_cells": args.all_problems or args.merged_cells,
    }

    # Run async pipeline
    asyncio.run(
        generate_benchmark_async(
            num_claims=args.num_claims,
            output_prefix=args.output,
            problems=problems,
            seed=args.seed,
        )
    )


if __name__ == "__main__":
    main()
