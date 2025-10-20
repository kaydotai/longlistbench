#!/usr/bin/env python3
"""
Check which problems are actually present in the ground truth data.
"""

import json
from pathlib import Path
from collections import Counter, defaultdict


def check_duplicates(claims):
    """Check if there are exact duplicate claims."""
    # Compare by key fields
    signatures = []
    for claim in claims:
        sig = (
            claim.get('incident_number'),
            claim.get('reference_number'),
            claim.get('date_of_loss'),
            claim.get('company_name')
        )
        signatures.append(sig)
    
    counts = Counter(signatures)
    duplicates = [sig for sig, count in counts.items() if count > 1]
    return len(duplicates) > 0, duplicates


def check_page_breaks(sample_name):
    """Check if OCR shows claims split across pages."""
    ocr_path = Path(f"claims/{sample_name}_ocr.md")
    if not ocr_path.exists():
        return None, "No OCR file"
    
    content = ocr_path.read_text()
    pages = content.split("# Page")
    
    # Look for incidents that span pages
    # (e.g., incident starts on one page, continues on next)
    split_incidents = []
    for i, page in enumerate(pages[1:], 1):  # Skip first split
        if "Incident #" in page:
            # Count how many incidents are on this page
            incidents = page.count("Incident #")
            # Check if page ends mid-incident (no complete financial table)
            lines = page.split('\n')
            if incidents > 0 and not any('Incident Total' in line for line in lines[-10:]):
                split_incidents.append(i)
    
    return len(split_incidents) > 0, split_incidents


def check_multiple_tables(claims_data, sample_name):
    """Check if document has multiple tables/sections."""
    ocr_path = Path(f"claims/{sample_name}_ocr.md")
    if not ocr_path.exists():
        return None, "No OCR file"
    
    content = ocr_path.read_text()
    
    # Look for multiple table sections
    csv_blocks = content.count("```csv")
    table_headers = content.count("Incident #")
    
    has_multiple = csv_blocks > 1 or table_headers > 2
    return has_multiple, f"{csv_blocks} CSV blocks, {table_headers} headers"


def check_multi_column(sample_name):
    """Check for multi-column layout indicators."""
    ocr_path = Path(f"claims/{sample_name}_ocr.md")
    if not ocr_path.exists():
        return None, "No OCR file"
    
    content = ocr_path.read_text()
    
    # Look for research paper style indicators
    indicators = [
        'Column 1' in content or 'Column 2' in content,
        content.count('Abstract') > 0,
        content.count('Introduction') > 0,
    ]
    
    return any(indicators), indicators


def check_large_document(claims):
    """Check if document is large (50+ claims)."""
    return len(claims) >= 50, len(claims)


def check_multi_row_entities(claims):
    """Check for fields with newlines."""
    multi_row_found = []
    for claim in claims:
        desc = claim.get('description', '')
        if '\n' in desc:
            multi_row_found.append(claim.get('incident_number'))
    
    return len(multi_row_found) > 0, multi_row_found


def main():
    claims_dir = Path(__file__).parent / "claims"
    
    # Find all ground truth files
    json_files = sorted([f for f in claims_dir.glob("*.json") 
                        if f.stem != "metadata" and "predicted" not in f.stem])
    
    print("="*80)
    print("PROBLEM DETECTION IN GROUND TRUTH DATA")
    print("="*80)
    print()
    
    results = defaultdict(list)
    
    for json_path in json_files[:10]:  # Test first 10
        sample_name = json_path.stem
        
        # Skip if already tested
        if sample_name.startswith('extreme'):
            continue
            
        with open(json_path) as f:
            claims = json.load(f)
        
        print(f"{sample_name} ({len(claims)} claims)")
        print("-" * 80)
        
        # Check each problem
        has_dup, dup_data = check_duplicates(claims)
        has_large, size = check_large_document(claims)
        has_multi_row, mr_data = check_multi_row_entities(claims)
        
        # Only check these if OCR exists
        has_page_breaks, pb_data = check_page_breaks(sample_name)
        has_multi_table, mt_data = check_multiple_tables(claims, sample_name)
        has_multi_col, mc_data = check_multi_column(sample_name)
        
        problems = []
        if has_dup:
            problems.append(f"✓ Duplicates ({len(dup_data)} sets)")
            results['duplicates'].append(sample_name)
        if has_large:
            problems.append(f"✓ Large doc ({size} claims)")
            results['large_doc'].append(sample_name)
        if has_multi_row:
            problems.append(f"✓ Multi-row ({len(mr_data)} claims)")
            results['multi_row'].append(sample_name)
        if has_page_breaks:
            problems.append(f"✓ Page breaks (pages {pb_data})")
            results['page_breaks'].append(sample_name)
        if has_multi_table:
            problems.append(f"✓ Multiple tables ({mt_data})")
            results['multiple_tables'].append(sample_name)
        if has_multi_col:
            problems.append(f"✓ Multi-column")
            results['multi_column'].append(sample_name)
        
        if problems:
            for p in problems:
                print(f"  {p}")
        else:
            print("  No problems detected")
        
        print()
    
    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)
    for problem, samples in sorted(results.items()):
        print(f"{problem:20s}: {len(samples)} samples")
    print()
    
    # Recommendations
    print("Samples to test for each problem:")
    print("-" * 80)
    for problem, samples in sorted(results.items()):
        if samples:
            print(f"{problem:20s}: {samples[0]}")


if __name__ == "__main__":
    main()
