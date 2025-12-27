#!/usr/bin/env python3
"""Generate complete benchmark dataset with OCR applied.

This script generates the full benchmark suite across all difficulty tiers:
- Easy: 10 claims each, 15 instances
- Medium: 25 claims each, 12 instances  
- Hard: 50 claims each, 8 instances
- Extreme: 100 claims each, 5 instances

Total: 40 instances, 1,350 claims
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

# Import from synthetic modules
import sys
sys.path.insert(0, str(Path(__file__).parent / "synthetic"))

from generate_claim_data import generate_incidents, write_json
from generate_html import LossRunHTMLGenerator
from html_to_pdf import html_to_pdf


# Benchmark configuration
BENCHMARK_CONFIG = {
    "easy": {
        "claims_per_pdf": 10,
        "num_instances": 15,
        "problem_combinations": [
            {"multi_row": True},
            {"page_breaks": True},
            {"multi_row": True, "page_breaks": True},
            {"duplicates": True},
            {"multi_row": True, "duplicates": True},
        ],
    },
    "medium": {
        "claims_per_pdf": 25,
        "num_instances": 12,
        "problem_combinations": [
            {"page_breaks": True, "multi_row": True, "duplicates": True},
            {"page_breaks": True, "multi_row": True, "multiple_tables": True},
            {"multi_row": True, "duplicates": True, "multiple_tables": True},
            {"page_breaks": True, "duplicates": True, "multiple_tables": True},
        ],
    },
    "hard": {
        "claims_per_pdf": 50,
        "num_instances": 8,
        "problem_combinations": [
            {
                "page_breaks": True,
                "multi_row": True,
                "duplicates": True,
                "multiple_tables": True,
                "multi_column": True,
            },
            {
                "page_breaks": True,
                "multi_row": True,
                "duplicates": True,
                "multiple_tables": True,
                "merged_cells": True,
            },
            {
                "page_breaks": True,
                "multi_row": True,
                "duplicates": True,
                "multi_column": True,
                "merged_cells": True,
            },
        ],
    },
    "extreme": {
        "claims_per_pdf": 100,
        "num_instances": 5,
        "problem_combinations": [
            {
                "page_breaks": True,
                "multi_row": True,
                "duplicates": True,
                "large_doc": True,
                "multiple_tables": True,
                "multi_column": True,
                "merged_cells": True,
            },
        ],
    },
}


async def generate_instance(
    tier: str,
    instance_num: int,
    num_claims: int,
    problems: dict[str, bool],
    output_dir: Path,
    base_seed: int,
    format: str = "detailed",
) -> dict[str, Any]:
    """Generate a single benchmark instance.
    
    Args:
        tier: Difficulty tier (easy, medium, hard, extreme)
        instance_num: Instance number within tier
        num_claims: Number of claims to generate
        problems: Problem flags to enable
        output_dir: Output directory
        base_seed: Base random seed
        format: Output format ('detailed' or 'table')
        
    Returns:
        Instance metadata dictionary
    """
    # Create instance ID and paths
    format_suffix = "_table" if format == "table" else "_detailed"
    instance_id = f"{tier}_{num_claims}_{instance_num:03d}{format_suffix}"
    json_path = output_dir / f"{instance_id}.json"
    html_path = output_dir / f"{instance_id}.html"
    pdf_path = output_dir / f"{instance_id}.pdf"
    
    # Use unique seed for each instance
    seed_material = f"{base_seed}:{instance_id}".encode("utf-8")
    seed_offset = int(hashlib.md5(seed_material).hexdigest()[:8], 16) % 10000
    seed = base_seed + seed_offset
    
    print(f"\n{'='*60}")
    print(f"Generating: {instance_id}")
    print(f"{'='*60}")
    
    # Step 1: Generate structured incidents data
    print(f"[1/3] Generating {num_claims} claims (seed={seed})...")
    incidents = generate_incidents(num_claims, seed=seed, start_year=2023)
    
    # Step 2: Generate HTML with problems
    print(f"[2/3] Generating HTML with problems (format={format})...")
    generator = LossRunHTMLGenerator(seed=seed, format=format)
    incidents_dicts = [i.model_dump() for i in incidents]
    incidents_dicts = generator.apply_document_problems(incidents_dicts, problems)
    json_path.write_text(json.dumps(incidents_dicts, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✓ Saved {len(incidents_dicts)} incidents → {json_path}")

    html_content = generator.generate(incidents_dicts, problems=problems)
    html_path.write_text(html_content, encoding="utf-8")
    
    enabled_problems = [k for k, v in problems.items() if v]
    print(f"  ✓ Problems enabled: {', '.join(enabled_problems) if enabled_problems else 'none'}")
    
    # Step 3: Render PDF
    print("[3/3] Rendering PDF...")
    await html_to_pdf(html_path, pdf_path)
    
    # Get file sizes
    json_size = json_path.stat().st_size
    pdf_size = pdf_path.stat().st_size
    pdf_pages = estimate_pages(len(incidents_dicts), problems)
    
    print(f"  ✓ Generated: {instance_id}.pdf ({pdf_pages} pages, {pdf_size / 1024:.1f} KB)")
    
    # Create metadata for this instance
    metadata = {
        "id": instance_id,
        "difficulty": tier,
        "format": format,
        "num_claims": len(incidents_dicts),
        "pages_estimate": pdf_pages,
        "problems": enabled_problems,
        "has_duplicates": problems.get("duplicates", False),
        "seed": seed,
        "files": {
            "ground_truth": f"{instance_id}.json",
            "pdf": f"{instance_id}.pdf",
            "json_size_bytes": json_size,
            "pdf_size_bytes": pdf_size,
        },
    }
    
    return metadata


def estimate_pages(num_claims: int, problems: dict[str, bool]) -> int:
    """Estimate number of pages based on claims and problems."""
    base_claims_per_page = 8
    
    # Adjust for problems that increase page count
    if problems.get("multi_row"):
        base_claims_per_page *= 0.7
    if problems.get("page_breaks"):
        base_claims_per_page *= 0.8
    if problems.get("multi_column"):
        base_claims_per_page *= 1.5
    if problems.get("multiple_tables"):
        # Adds extra tables
        return max(3, int(num_claims / base_claims_per_page) + 2)
    
    return max(2, int(num_claims / base_claims_per_page))


async def generate_tier(
    tier: str,
    config: dict[str, Any],
    output_dir: Path,
    base_seed: int,
) -> list[dict[str, Any]]:
    """Generate all instances for a difficulty tier.
    
    Args:
        tier: Difficulty tier name
        config: Tier configuration
        output_dir: Output directory
        base_seed: Base random seed
        
    Returns:
        List of instance metadata dictionaries
    """
    print(f"\n{'#'*60}")
    print(f"# Generating {tier.upper()} tier")
    print(f"#   {config['claims_per_pdf']} claims/PDF × {config['num_instances']} instances × 2 formats")
    print(f"{'#'*60}")
    
    instances_metadata = []
    problem_combinations = config["problem_combinations"]
    
    for i in range(config["num_instances"]):
        # Cycle through problem combinations
        problems = problem_combinations[i % len(problem_combinations)]
        
        # Generate both formats (detailed and table) for each instance
        for format in ["detailed", "table"]:
            metadata = await generate_instance(
                tier=tier,
                instance_num=i + 1,
                num_claims=config["claims_per_pdf"],
                problems=problems,
                output_dir=output_dir,
                base_seed=base_seed,
                format=format,
            )
            instances_metadata.append(metadata)
    
    return instances_metadata


async def generate_all_benchmarks(
    output_dir: Path,
    base_seed: int = 42,
    tiers: list[str] | None = None,
) -> None:
    """Generate complete benchmark dataset.
    
    Args:
        output_dir: Output directory for benchmark data
        base_seed: Base random seed for reproducibility
        tiers: List of tiers to generate (default: all)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine which tiers to generate
    if tiers is None:
        tiers = ["easy", "medium", "hard", "extreme"]
    
    print(f"\n{'='*60}")
    print("LOST-AND-FOUND ENTITIES BENCHMARK GENERATOR")
    print(f"{'='*60}")
    print(f"Output directory: {output_dir}")
    print(f"Base seed: {base_seed}")
    print(f"Tiers: {', '.join(tiers)}")
    print(f"{'='*60}")
    
    # Generate all tiers
    all_instances = []
    total_claims = 0
    
    for tier in tiers:
        if tier not in BENCHMARK_CONFIG:
            print(f"Warning: Unknown tier '{tier}', skipping...")
            continue
            
        config = BENCHMARK_CONFIG[tier]
        instances = await generate_tier(tier, config, output_dir, base_seed)
        all_instances.extend(instances)
        total_claims += sum(i["num_claims"] for i in instances)
    
    # Generate metadata file
    metadata = {
        "dataset_name": "lost-and-found-entities-v1",
        "version": "1.0.0",
        "description": "Benchmark for long-list entity extraction from insurance claims",
        "generated_at": datetime.now().isoformat(),
        "base_seed": base_seed,
        "total_instances": len(all_instances),
        "total_claims": total_claims,
        "schema_version": "1.0",
        "difficulty_tiers": {
            tier: {
                "claims_per_pdf": BENCHMARK_CONFIG[tier]["claims_per_pdf"],
                "num_instances": BENCHMARK_CONFIG[tier]["num_instances"],
                "total_claims": sum(
                    i["num_claims"] for i in all_instances if i["difficulty"] == tier
                ),
            }
            for tier in BENCHMARK_CONFIG.keys()
        },
        "instances": all_instances,
    }
    
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    
    print(f"\n{'='*60}")
    print("✓ BENCHMARK GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"Total instances: {len(all_instances)}")
    print(f"Total claims: {total_claims}")
    print(f"Metadata: {metadata_path}")
    print(f"{'='*60}\n")
    
    # Print summary by tier
    print("\nSummary by tier:")
    for tier in ["easy", "medium", "hard", "extreme"]:
        tier_instances = [i for i in all_instances if i["difficulty"] == tier]
        if tier_instances:
            detailed = len([i for i in tier_instances if i["format"] == "detailed"])
            table = len([i for i in tier_instances if i["format"] == "table"])
            tier_claims = sum(i["num_claims"] for i in tier_instances)
            print(f"  {tier:8s}: {len(tier_instances):2d} instances ({detailed} detailed + {table} table), {tier_claims:4d} claims")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate complete benchmark dataset for Lost-and-Found Entities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate all tiers
  python generate_claims_benchmark.py

  # Generate specific tiers only
  python generate_claims_benchmark.py --tiers easy medium

  # Custom output directory
  python generate_claims_benchmark.py -o benchmarks/claims_v2

  # Custom seed for different dataset
  python generate_claims_benchmark.py -s 12345
        """,
    )
    
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="claims",
        help="Output directory (default: claims/)",
    )
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        default=42,
        help="Base random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--tiers",
        nargs="+",
        choices=["easy", "medium", "hard", "extreme"],
        help="Specific tiers to generate (default: all)",
    )
    
    args = parser.parse_args()
    
    output_dir = Path(__file__).parent / args.output
    
    asyncio.run(
        generate_all_benchmarks(
            output_dir=output_dir,
            base_seed=args.seed,
            tiers=args.tiers,
        )
    )


if __name__ == "__main__":
    main()
