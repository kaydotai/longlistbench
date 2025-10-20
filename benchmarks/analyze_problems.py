#!/usr/bin/env python3
"""
Analyze which problems are present in each benchmark sample
and correlate with extraction performance.
"""

import json
from pathlib import Path
from collections import defaultdict


def load_metadata():
    """Load benchmark metadata."""
    metadata_path = Path(__file__).parent / "claims" / "metadata.json"
    with open(metadata_path, 'r') as f:
        return json.load(f)


def get_sample_problems(metadata, sample_id: str) -> dict:
    """Get problem information for a specific sample."""
    for instance in metadata['instances']:
        if instance['id'] == sample_id:
            return {
                'id': instance['id'],
                'difficulty': instance['difficulty'],
                'num_claims': instance['num_claims'],
                'pages_estimate': instance.get('pages_estimate', 'N/A'),
                'problems': instance.get('problems', []),
                'has_duplicates': instance.get('has_duplicates', False),
            }
    return None


def main():
    print("="*70)
    print("BENCHMARK PROBLEM ANALYSIS")
    print("="*70)
    print()
    
    # Load metadata
    metadata = load_metadata()
    
    print(f"Dataset: {metadata['dataset_name']}")
    print(f"Version: {metadata['version']}")
    print(f"Total Instances: {metadata['total_instances']}")
    print(f"Total Claims: {metadata['total_claims']}")
    print()
    
    # Analyze our test samples
    test_samples = [
        "easy_10_001",
        "medium_25_001", 
        "extreme_100_001",
    ]
    
    print("Problem Distribution in Test Samples:")
    print("-" * 70)
    
    for sample_id in test_samples:
        info = get_sample_problems(metadata, sample_id)
        if not info:
            print(f"⚠ {sample_id} not found in metadata")
            continue
        
        print(f"\n{sample_id} ({info['difficulty'].upper()})")
        print(f"  Claims: {info['num_claims']}")
        print(f"  Pages: ~{info['pages_estimate']}")
        print(f"  Duplicates: {'Yes' if info['has_duplicates'] else 'No'}")
        print(f"  Problems: {', '.join(info['problems']) if info['problems'] else 'None'}")
    
    print()
    print("="*70)
    print("PROBLEM TYPE REFERENCE")
    print("="*70)
    print()
    print("1. page_breaks       - Table rows split across page boundaries")
    print("2. multi_row         - Cells with line breaks (addresses, descriptions)")
    print("3. duplicates        - Identical claim records appearing multiple times")
    print("4. large_document    - High volume of records (100+ claims)")
    print("5. multiple_tables   - Relevant claims mixed with irrelevant content")
    print("6. multi_column      - Research paper style formatting")
    print("7. merged_cells      - Cells spanning multiple columns/rows")
    print()
    print("Expected Issues:")
    print("- Page breaks: Claims split across pages may be missed or duplicated")
    print("- Multi-row: Line breaks in cells can confuse extraction")
    print("- Duplicates: Must detect true duplicates vs. similar records")
    print("- Large docs: Context window limits, need chunking strategies")
    print("- Multiple tables: Must distinguish relevant from irrelevant data")
    print("- Multi-column: Layout reconstruction challenges")
    print("- Merged cells: Column alignment issues in OCR")
    print()
    
    # Count problem frequency
    problem_counts = defaultdict(int)
    for instance in metadata['instances']:
        for problem in instance.get('problems', []):
            problem_counts[problem] += 1
        if instance.get('has_duplicates'):
            problem_counts['duplicates'] += 1
    
    print("Problem Frequency Across All Instances:")
    print("-" * 70)
    for problem, count in sorted(problem_counts.items(), key=lambda x: -x[1]):
        print(f"  {problem:20s}: {count:3d} instances")


if __name__ == "__main__":
    main()
