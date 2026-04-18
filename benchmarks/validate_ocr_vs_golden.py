#!/usr/bin/env python3
"""
Validate OCR output against golden JSON data.

This script checks whether key identifiers from the golden JSON
(incident_number, reference_number) appear in the OCR markdown text.
It reports coverage metrics and lists missing identifiers.
"""

import json
import re
from pathlib import Path


def load_golden(json_path: Path) -> list[dict]:
    """Load golden claims from JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_ocr_text(md_path: Path) -> str:
    """Load OCR text from markdown file."""
    return md_path.read_text(encoding="utf-8")


def extract_identifiers(claims: list[dict]) -> dict[str, set[str]]:
    """Extract key identifiers from golden claims."""
    incident_numbers = set()
    reference_numbers = set()
    
    for claim in claims:
        inc_num = claim.get("incident_number", "")
        if inc_num:
            # Store both raw and numeric-only versions
            incident_numbers.add(inc_num)
            # Extract just the number part (e.g., "30001" from "#30001")
            match = re.search(r"\d+", inc_num)
            if match:
                incident_numbers.add(match.group())
        
        ref_num = claim.get("reference_number", "")
        if ref_num:
            reference_numbers.add(ref_num)
    
    return {
        "incident_numbers": incident_numbers,
        "reference_numbers": reference_numbers,
    }


def check_coverage(ocr_text: str, identifiers: dict[str, set[str]]) -> dict:
    """Check how many identifiers appear in the OCR text."""
    results = {}
    
    for id_type, id_set in identifiers.items():
        found = set()
        missing = set()
        
        for identifier in id_set:
            # Check if identifier appears in OCR text
            if identifier in ocr_text:
                found.add(identifier)
            else:
                missing.add(identifier)
        
        total = len(id_set)
        found_count = len(found)
        coverage = found_count / total if total > 0 else 0
        
        results[id_type] = {
            "total": total,
            "found": found_count,
            "missing": len(missing),
            "coverage": coverage,
            "missing_ids": sorted(missing)[:10],  # First 10 missing
        }
    
    return results


def validate_sample(sample_name: str, claims_dir: Path, verbose: bool = False) -> dict | None:
    """Validate a single sample's OCR against golden data."""
    json_path = claims_dir / f"{sample_name}.json"
    ocr_path = claims_dir / f"{sample_name}_ocr.md"
    
    if not json_path.exists():
        return None
    
    if not ocr_path.exists():
        return {"error": "OCR file not found", "sample": sample_name}
    
    # Load data
    claims = load_golden(json_path)
    ocr_text = load_ocr_text(ocr_path)
    
    # Extract identifiers and check coverage
    identifiers = extract_identifiers(claims)
    coverage = check_coverage(ocr_text, identifiers)
    
    result = {
        "sample": sample_name,
        "num_claims": len(claims),
        "ocr_chars": len(ocr_text),
        "incident_coverage": coverage["incident_numbers"]["coverage"],
        "reference_coverage": coverage["reference_numbers"]["coverage"],
        "incident_missing": coverage["incident_numbers"]["missing"],
        "reference_missing": coverage["reference_numbers"]["missing"],
    }
    
    if verbose:
        result["missing_incident_ids"] = coverage["incident_numbers"]["missing_ids"]
        result["missing_reference_ids"] = coverage["reference_numbers"]["missing_ids"]
    
    return result


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Validate OCR output against golden JSON data"
    )
    parser.add_argument(
        "--claims-dir",
        type=str,
        default="claims",
        help="Directory containing claims data (default: claims/)",
    )
    parser.add_argument(
        "--sample",
        type=str,
        help="Validate a specific sample (e.g., 'easy_10_001_detailed')",
    )
    parser.add_argument(
        "--tiers",
        nargs="+",
        choices=["easy", "medium", "hard", "extreme"],
        help="Only validate samples whose filename starts with one of these tiers",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show missing identifiers",
    )
    
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    claims_dir = script_dir / args.claims_dir
    
    if not claims_dir.exists():
        print(f"Error: Claims directory not found: {claims_dir}")
        return
    
    # Find samples to validate
    if args.sample:
        samples = [args.sample]
    else:
        # Find all samples with OCR files
        ocr_files = sorted(claims_dir.glob("*_ocr.md"))
        samples = [f.stem.replace("_ocr", "") for f in ocr_files]

    if args.tiers and not args.sample:
        samples = [
            s
            for s in samples
            if any(s.startswith(f"{tier}_") for tier in args.tiers)
        ]
    
    if not samples:
        print("No OCR files found. Run ocr_claims_pdfs.py first.")
        return
    
    print("=" * 70)
    print("OCR vs GOLDEN VALIDATION")
    print("=" * 70)
    print()
    
    results = []
    total_claims = 0
    total_incident_found = 0
    total_reference_found = 0
    
    for sample in samples:
        result = validate_sample(sample, claims_dir, verbose=args.verbose)
        
        if result is None:
            continue
        
        if "error" in result:
            print(f"⚠ {sample}: {result['error']}")
            continue
        
        results.append(result)
        
        inc_cov = result["incident_coverage"]
        ref_cov = result["reference_coverage"]
        
        # Determine status emoji
        if inc_cov >= 0.95 and ref_cov >= 0.95:
            status = "✓"
        elif inc_cov >= 0.80 and ref_cov >= 0.80:
            status = "~"
        else:
            status = "✗"
        
        print(f"{status} {sample}")
        print(f"    Claims: {result['num_claims']:4d}  |  "
              f"Incident: {inc_cov:5.1%} ({result['incident_missing']} missing)  |  "
              f"Reference: {ref_cov:5.1%} ({result['reference_missing']} missing)")
        
        if args.verbose and result.get("missing_incident_ids"):
            print(f"    Missing incidents: {', '.join(result['missing_incident_ids'][:5])}")
        if args.verbose and result.get("missing_reference_ids"):
            print(f"    Missing references: {', '.join(result['missing_reference_ids'][:5])}")
        
        total_claims += result["num_claims"]
        # Approximate found counts
        total_incident_found += int(inc_cov * result["num_claims"])
        total_reference_found += int(ref_cov * result["num_claims"])
    
    if results:
        print()
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        
        avg_inc = sum(r["incident_coverage"] for r in results) / len(results)
        avg_ref = sum(r["reference_coverage"] for r in results) / len(results)
        
        print(f"Samples validated: {len(results)}")
        print(f"Total claims: {total_claims}")
        print(f"Average incident coverage: {avg_inc:.1%}")
        print(f"Average reference coverage: {avg_ref:.1%}")
        
        # Count by coverage level
        high = sum(1 for r in results if r["incident_coverage"] >= 0.95)
        medium = sum(1 for r in results if 0.80 <= r["incident_coverage"] < 0.95)
        low = sum(1 for r in results if r["incident_coverage"] < 0.80)
        
        print(f"\nCoverage breakdown:")
        print(f"  ≥95%: {high} samples")
        print(f"  80-95%: {medium} samples")
        print(f"  <80%: {low} samples")


if __name__ == "__main__":
    main()
