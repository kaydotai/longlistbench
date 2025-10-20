#!/usr/bin/env python3
"""
Simple extraction test to identify which problems affect extraction quality.
Tests basic LLM prompting approaches on OCR'd benchmark samples.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


def setup_gemini():
    """Configure Gemini API."""
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key or api_key == 'your-api-key-here':
        print("Error: GEMINI_API_KEY not set in .env file.")
        sys.exit(1)
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.0-flash-exp')


def load_ground_truth(json_path: Path) -> list[dict]:
    """Load ground truth claims from JSON file."""
    with open(json_path, 'r') as f:
        return json.load(f)


def load_ocr_text(md_path: Path) -> str:
    """Load OCR'd text from markdown file."""
    return md_path.read_text(encoding='utf-8')


def extract_claims_zero_shot(model, ocr_text: str) -> list[dict]:
    """
    Simple zero-shot extraction using LLM.
    This is intentionally naive to expose problems.
    """
    prompt = f"""Extract all insurance claims from the following document.

For each claim, extract these fields:
- incident_number
- company_name
- date_of_loss
- status (Open/Closed)
- driver_name
- coverage_type
- total_incurred (sum of all financial amounts)

Return the results as a JSON array. Only return the JSON, no explanations.

Document:
{ocr_text}
"""
    
    try:
        response = model.generate_content(prompt)
        # Try to parse JSON from response
        response_text = response.text.strip()
        # Remove markdown code blocks if present
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
        response_text = response_text.strip()
        
        return json.loads(response_text)
    except Exception as e:
        print(f"  ⚠ Extraction error: {e}")
        return []


def normalize_incident_number(incident_num: str) -> str:
    """Normalize incident number for comparison."""
    if not incident_num:
        return ""
    # Extract just the number part
    incident_num = str(incident_num).strip()
    # Remove common prefixes
    for prefix in ['Incident #', 'Incident#', 'Incident ', '#', 'INC']:
        if incident_num.startswith(prefix):
            incident_num = incident_num[len(prefix):]
    return incident_num.strip()


def evaluate_extraction(predicted: list[dict], ground_truth: list[dict], verbose: bool = False) -> dict[str, Any]:
    """
    Simple evaluation metrics with normalized matching.
    """
    gt_count = len(ground_truth)
    pred_count = len(predicted)
    
    # Normalize incident numbers for matching
    gt_incidents = {}
    for claim in ground_truth:
        inc_num = claim.get('incident_number', '')
        if inc_num:
            normalized = normalize_incident_number(inc_num)
            gt_incidents[normalized] = claim
    
    pred_incidents = {}
    for claim in predicted:
        inc_num = claim.get('incident_number', '')
        if inc_num:
            normalized = normalize_incident_number(inc_num)
            pred_incidents[normalized] = claim
    
    found = len(set(gt_incidents.keys()) & set(pred_incidents.keys()))
    
    recall = found / gt_count if gt_count > 0 else 0
    precision = found / pred_count if pred_count > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    missing = set(gt_incidents.keys()) - set(pred_incidents.keys())
    extra = set(pred_incidents.keys()) - set(gt_incidents.keys())
    
    result = {
        'ground_truth_count': gt_count,
        'predicted_count': pred_count,
        'found': found,
        'recall': recall,
        'precision': precision,
        'f1': f1,
        'missing': len(missing),
        'extra': len(extra),
    }
    
    if verbose:
        result['missing_ids'] = sorted(missing)
        result['extra_ids'] = sorted(extra)
        result['found_ids'] = sorted(set(gt_incidents.keys()) & set(pred_incidents.keys()))
    
    return result


def main():
    # Setup
    script_dir = Path(__file__).parent
    claims_dir = script_dir / "claims"
    
    # Test samples that exist (from our OCR test)
    test_samples = []
    
    # Add all samples with OCR
    for ocr_file in sorted(claims_dir.glob("*_ocr.md")):
        sample = ocr_file.stem.replace("_ocr", "")
        if ocr_file.stat().st_size > 0:  # Skip empty files
            test_samples.append(sample)
    
    print("="*70)
    print("EXTRACTION TEST: Zero-Shot LLM Prompting")
    print("="*70)
    print()
    
    # Setup Gemini
    print("Setting up Gemini API...")
    model = setup_gemini()
    print("✓ Model configured")
    print()
    
    results = []
    
    for sample in test_samples:
        print(f"Testing: {sample}")
        print("-" * 70)
        
        # Load files
        ocr_path = claims_dir / f"{sample}_ocr.md"
        json_path = claims_dir / f"{sample}.json"
        
        if not ocr_path.exists():
            print(f"  ⚠ OCR file not found: {ocr_path}")
            continue
            
        if not json_path.exists():
            print(f"  ⚠ Ground truth not found: {json_path}")
            continue
        
        # Load data
        ocr_text = load_ocr_text(ocr_path)
        ground_truth = load_ground_truth(json_path)
        
        print(f"  Ground truth: {len(ground_truth)} claims")
        print(f"  OCR text: {len(ocr_text):,} characters")
        
        # Extract
        print(f"  Extracting with LLM...")
        predicted = extract_claims_zero_shot(model, ocr_text)
        
        # Save predictions for debugging
        debug_path = claims_dir / f"{sample}_predicted.json"
        with open(debug_path, 'w') as f:
            json.dump(predicted, f, indent=2)
        
        # Evaluate
        metrics = evaluate_extraction(predicted, ground_truth, verbose=True)
        
        print(f"  Predicted: {metrics['predicted_count']} claims")
        print(f"  Found: {metrics['found']} / {metrics['ground_truth_count']}")
        print(f"  Recall: {metrics['recall']:.1%}")
        print(f"  Precision: {metrics['precision']:.1%}")
        print(f"  F1: {metrics['f1']:.1%}")
        
        if metrics['missing'] > 0:
            print(f"  ⚠ Missing: {metrics['missing']} claims not found")
            if metrics.get('missing_ids'):
                print(f"     Missing IDs: {', '.join(metrics['missing_ids'][:5])}")
        if metrics['extra'] > 0:
            print(f"  ⚠ Extra: {metrics['extra']} spurious extractions")
            if metrics.get('extra_ids'):
                print(f"     Extra IDs: {', '.join(metrics['extra_ids'][:5])}")
        if metrics['found'] > 0 and metrics.get('found_ids'):
            print(f"  ✓ Found IDs: {', '.join(sorted(metrics['found_ids'])[:5])}")
        
        results.append({
            'sample': sample,
            'metrics': metrics,
        })
        
        print()
    
    # Summary
    print("="*70)
    print("SUMMARY")
    print("="*70)
    
    for result in results:
        sample = result['sample']
        m = result['metrics']
        status = "✓" if m['f1'] > 0.9 else "⚠" if m['f1'] > 0.5 else "✗"
        print(f"{status} {sample:30s} F1: {m['f1']:5.1%}  Recall: {m['recall']:5.1%}  ({m['found']}/{m['ground_truth_count']})")
    
    print()
    print("Next steps:")
    print("- Check which problems (page breaks, duplicates, etc.) correlate with low scores")
    print("- Test chunking strategies for large documents")
    print("- Test accumulative generation for better recall")


if __name__ == "__main__":
    main()
