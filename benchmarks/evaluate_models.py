#!/usr/bin/env python3
"""Multi-model evaluation script for the LongListBench benchmark.

Runs extraction tests on Gemini, GPT-4, and Claude using the same prompts.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

# ============================================================================
# Model Clients
# ============================================================================

@dataclass
class ModelConfig:
    name: str
    provider: str
    model_id: str
    setup_fn: Callable
    extract_fn: Callable


def setup_gemini():
    """Configure Gemini API."""
    import google.generativeai as genai
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in environment")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.0-flash-exp')


def setup_openai():
    """Configure OpenAI API."""
    from openai import OpenAI
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in environment")
    return OpenAI(api_key=api_key)


def setup_anthropic():
    """Configure Anthropic API."""
    import anthropic
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in environment")
    return anthropic.Anthropic(api_key=api_key)


# ============================================================================
# Extraction Functions
# ============================================================================

EXTRACTION_PROMPT = """Extract all incident records from the following document.

For each incident, extract these fields:
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


def parse_json_response(response_text: str) -> list[dict]:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = response_text.strip()
    # Remove markdown code blocks if present
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    text = text.strip()
    return json.loads(text)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=4, min=10, max=120))
def extract_with_gemini(client, ocr_text: str) -> list[dict]:
    """Extract claims using Gemini."""
    prompt = EXTRACTION_PROMPT.format(ocr_text=ocr_text)
    response = client.generate_content(prompt)
    return parse_json_response(response.text)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=60))
def extract_with_openai(client, ocr_text: str) -> list[dict]:
    """Extract claims using OpenAI GPT-4."""
    prompt = EXTRACTION_PROMPT.format(ocr_text=ocr_text)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return parse_json_response(response.choices[0].message.content)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=60))
def extract_with_anthropic(client, ocr_text: str) -> list[dict]:
    """Extract claims using Anthropic Claude."""
    prompt = EXTRACTION_PROMPT.format(ocr_text=ocr_text)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_json_response(response.content[0].text)


# Model configurations
MODELS = {
    'gemini': ModelConfig(
        name='Gemini 2.0 Flash',
        provider='Google',
        model_id='gemini-2.0-flash-exp',
        setup_fn=setup_gemini,
        extract_fn=extract_with_gemini,
    ),
    'gpt4': ModelConfig(
        name='GPT-4o',
        provider='OpenAI',
        model_id='gpt-4o',
        setup_fn=setup_openai,
        extract_fn=extract_with_openai,
    ),
    'claude': ModelConfig(
        name='Claude Sonnet 4',
        provider='Anthropic',
        model_id='claude-sonnet-4-20250514',
        setup_fn=setup_anthropic,
        extract_fn=extract_with_anthropic,
    ),
}


# ============================================================================
# Evaluation Logic
# ============================================================================

def normalize_incident_number(incident_num: str) -> str:
    """Normalize incident number for comparison."""
    if not incident_num:
        return ""
    incident_num = str(incident_num).strip()
    for prefix in ['Incident #', 'Incident#', 'Incident ', '#', 'INC']:
        if incident_num.startswith(prefix):
            incident_num = incident_num[len(prefix):]
    return incident_num.strip()


def evaluate_extraction(predicted: list[dict], ground_truth: list[dict]) -> dict[str, Any]:
    """Compute evaluation metrics."""
    gt_count = len(ground_truth)
    pred_count = len(predicted)
    
    gt_incidents = {
        normalize_incident_number(c.get('incident_number', '')): c
        for c in ground_truth if c.get('incident_number')
    }
    pred_incidents = {
        normalize_incident_number(c.get('incident_number', '')): c
        for c in predicted if c.get('incident_number')
    }
    
    found = len(set(gt_incidents.keys()) & set(pred_incidents.keys()))
    missing = set(gt_incidents.keys()) - set(pred_incidents.keys())
    extra = set(pred_incidents.keys()) - set(gt_incidents.keys())
    
    recall = found / gt_count if gt_count > 0 else 0
    precision = found / pred_count if pred_count > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    return {
        'ground_truth_count': gt_count,
        'predicted_count': pred_count,
        'found': found,
        'recall': recall,
        'precision': precision,
        'f1': f1,
        'missing': len(missing),
        'extra': len(extra),
        'missing_ids': sorted(missing),
        'extra_ids': sorted(extra),
    }


# ============================================================================
# Main Evaluation Runner
# ============================================================================

@dataclass
class EvaluationResult:
    model: str
    sample: str
    tier: str
    format: str
    metrics: dict
    extraction_time: float
    error: str = None


def get_sample_info(sample_name: str) -> tuple[str, str]:
    """Extract tier and format from sample name."""
    parts = sample_name.split('_')
    tier = parts[0]  # easy, medium, hard, extreme
    fmt = parts[-1]  # detailed, table
    return tier, fmt


def run_evaluation(
    models: list[str],
    samples: list[str] = None,
    tiers: list[str] = None,
    formats: list[str] = None,
    claims_dir: Path = None,
    output_dir: Path = None,
) -> list[EvaluationResult]:
    """Run evaluation across specified models and samples."""
    
    if claims_dir is None:
        claims_dir = Path(__file__).parent / "claims"
    if output_dir is None:
        output_dir = Path(__file__).parent / "results"
    
    output_dir.mkdir(exist_ok=True)
    
    # Discover available samples
    if samples is None:
        samples = []
        for ocr_file in sorted(claims_dir.glob("*_ocr.md")):
            sample = ocr_file.stem.replace("_ocr", "")
            json_file = claims_dir / f"{sample}.json"
            if json_file.exists() and ocr_file.stat().st_size > 0:
                tier, fmt = get_sample_info(sample)
                if (tiers is None or tier in tiers) and (formats is None or fmt in formats):
                    samples.append(sample)
    
    print(f"Evaluating {len(samples)} samples across {len(models)} models")
    print(f"Samples: {', '.join(samples[:5])}{'...' if len(samples) > 5 else ''}")
    print()
    
    # Setup models
    clients = {}
    for model_key in models:
        if model_key not in MODELS:
            print(f"⚠ Unknown model: {model_key}")
            continue
        config = MODELS[model_key]
        try:
            print(f"Setting up {config.name}...")
            clients[model_key] = config.setup_fn()
            print(f"  ✓ {config.name} ready")
        except Exception as e:
            print(f"  ✗ {config.name} failed: {e}")
    
    print()
    
    results = []
    
    for sample in samples:
        print(f"{'='*70}")
        print(f"Sample: {sample}")
        print(f"{'='*70}")
        
        tier, fmt = get_sample_info(sample)
        
        # Load data
        ocr_path = claims_dir / f"{sample}_ocr.md"
        json_path = claims_dir / f"{sample}.json"
        
        ocr_text = ocr_path.read_text(encoding='utf-8')
        with open(json_path) as f:
            ground_truth = json.load(f)
        
        print(f"  Ground truth: {len(ground_truth)} claims")
        print(f"  OCR text: {len(ocr_text):,} characters")
        print()
        
        for model_key in models:
            if model_key not in clients:
                continue
            
            config = MODELS[model_key]
            client = clients[model_key]
            
            print(f"  [{config.name}]")
            
            start_time = time.time()
            error = None
            predicted = []
            
            try:
                predicted = config.extract_fn(client, ocr_text)
            except Exception as e:
                error = str(e)
                print(f"    ✗ Error: {e}")
            
            # Rate limiting delay between model calls
            if model_key == 'gemini':
                time.sleep(5)
            
            extraction_time = time.time() - start_time
            
            if not error:
                metrics = evaluate_extraction(predicted, ground_truth)
                
                # Save predictions
                pred_path = output_dir / f"{sample}_{model_key}_predicted.json"
                with open(pred_path, 'w') as f:
                    json.dump(predicted, f, indent=2)
                
                print(f"    Predicted: {metrics['predicted_count']} claims")
                print(f"    Recall: {metrics['recall']:.1%}  Precision: {metrics['precision']:.1%}  F1: {metrics['f1']:.1%}")
                print(f"    Time: {extraction_time:.1f}s")
                
                if metrics['missing'] > 0:
                    print(f"    ⚠ Missing: {metrics['missing']}")
                if metrics['extra'] > 0:
                    print(f"    ⚠ Extra: {metrics['extra']}")
            else:
                metrics = {'recall': 0, 'precision': 0, 'f1': 0, 'found': 0, 
                          'ground_truth_count': len(ground_truth), 'predicted_count': 0,
                          'missing': len(ground_truth), 'extra': 0}
            
            results.append(EvaluationResult(
                model=model_key,
                sample=sample,
                tier=tier,
                format=fmt,
                metrics=metrics,
                extraction_time=extraction_time,
                error=error,
            ))
            
            print()
        
        # Rate limiting between samples
        time.sleep(1)
    
    return results


def generate_report(results: list[EvaluationResult], output_path: Path):
    """Generate summary report in JSON and Markdown formats."""
    
    # Aggregate by model
    model_stats = {}
    for r in results:
        if r.model not in model_stats:
            model_stats[r.model] = {
                'total_samples': 0,
                'total_f1': 0,
                'total_recall': 0,
                'total_precision': 0,
                'errors': 0,
                'by_tier': {},
                'by_format': {},
            }
        
        stats = model_stats[r.model]
        stats['total_samples'] += 1
        stats['total_f1'] += r.metrics['f1']
        stats['total_recall'] += r.metrics['recall']
        stats['total_precision'] += r.metrics['precision']
        if r.error:
            stats['errors'] += 1
        
        # By tier
        if r.tier not in stats['by_tier']:
            stats['by_tier'][r.tier] = {'count': 0, 'f1_sum': 0, 'recall_sum': 0}
        stats['by_tier'][r.tier]['count'] += 1
        stats['by_tier'][r.tier]['f1_sum'] += r.metrics['f1']
        stats['by_tier'][r.tier]['recall_sum'] += r.metrics['recall']
        
        # By format
        if r.format not in stats['by_format']:
            stats['by_format'][r.format] = {'count': 0, 'f1_sum': 0, 'recall_sum': 0}
        stats['by_format'][r.format]['count'] += 1
        stats['by_format'][r.format]['f1_sum'] += r.metrics['f1']
        stats['by_format'][r.format]['recall_sum'] += r.metrics['recall']
    
    # Compute averages
    for model, stats in model_stats.items():
        n = stats['total_samples']
        stats['avg_f1'] = stats['total_f1'] / n if n > 0 else 0
        stats['avg_recall'] = stats['total_recall'] / n if n > 0 else 0
        stats['avg_precision'] = stats['total_precision'] / n if n > 0 else 0
        
        for tier_stats in stats['by_tier'].values():
            c = tier_stats['count']
            tier_stats['avg_f1'] = tier_stats['f1_sum'] / c if c > 0 else 0
            tier_stats['avg_recall'] = tier_stats['recall_sum'] / c if c > 0 else 0
        
        for fmt_stats in stats['by_format'].values():
            c = fmt_stats['count']
            fmt_stats['avg_f1'] = fmt_stats['f1_sum'] / c if c > 0 else 0
            fmt_stats['avg_recall'] = fmt_stats['recall_sum'] / c if c > 0 else 0
    
    # Save JSON report
    report = {
        'timestamp': datetime.now().isoformat(),
        'model_stats': model_stats,
        'detailed_results': [
            {
                'model': r.model,
                'sample': r.sample,
                'tier': r.tier,
                'format': r.format,
                'metrics': r.metrics,
                'extraction_time': r.extraction_time,
                'error': r.error,
            }
            for r in results
        ],
    }
    
    json_path = output_path / 'evaluation_report.json'
    with open(json_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    # Generate Markdown report
    md_lines = [
        "# Multi-Model Evaluation Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Overall Results",
        "",
        "| Model | Avg F1 | Avg Recall | Avg Precision | Samples | Errors |",
        "|-------|--------|------------|---------------|---------|--------|",
    ]
    
    for model_key in ['gemini', 'gpt4', 'claude']:
        if model_key in model_stats:
            s = model_stats[model_key]
            name = MODELS[model_key].name
            md_lines.append(
                f"| {name} | {s['avg_f1']:.1%} | {s['avg_recall']:.1%} | "
                f"{s['avg_precision']:.1%} | {s['total_samples']} | {s['errors']} |"
            )
    
    md_lines.extend([
        "",
        "## Results by Difficulty Tier",
        "",
        "| Model | Easy | Medium | Hard | Extreme |",
        "|-------|------|--------|------|---------|",
    ])
    
    for model_key in ['gemini', 'gpt4', 'claude']:
        if model_key in model_stats:
            s = model_stats[model_key]
            name = MODELS[model_key].name
            tiers = ['easy', 'medium', 'hard', 'extreme']
            tier_scores = [
                f"{s['by_tier'].get(t, {}).get('avg_f1', 0):.1%}" for t in tiers
            ]
            md_lines.append(f"| {name} | {' | '.join(tier_scores)} |")
    
    md_lines.extend([
        "",
        "## Results by Document Format",
        "",
        "| Model | Detailed | Table |",
        "|-------|----------|-------|",
    ])
    
    for model_key in ['gemini', 'gpt4', 'claude']:
        if model_key in model_stats:
            s = model_stats[model_key]
            name = MODELS[model_key].name
            detailed = s['by_format'].get('detailed', {}).get('avg_f1', 0)
            table = s['by_format'].get('table', {}).get('avg_f1', 0)
            md_lines.append(f"| {name} | {detailed:.1%} | {table:.1%} |")
    
    md_lines.extend([
        "",
        "## Detailed Results",
        "",
    ])
    
    # Group by sample
    samples_seen = set()
    for r in results:
        if r.sample not in samples_seen:
            samples_seen.add(r.sample)
            md_lines.append(f"### {r.sample}")
            md_lines.append("")
            md_lines.append("| Model | F1 | Recall | Precision | Predicted | Time |")
            md_lines.append("|-------|-----|--------|-----------|-----------|------|")
            
            for r2 in results:
                if r2.sample == r.sample:
                    name = MODELS[r2.model].name
                    m = r2.metrics
                    if r2.error:
                        md_lines.append(f"| {name} | ERROR | - | - | - | - |")
                    else:
                        md_lines.append(
                            f"| {name} | {m['f1']:.1%} | {m['recall']:.1%} | "
                            f"{m['precision']:.1%} | {m['predicted_count']} | {r2.extraction_time:.1f}s |"
                        )
            
            md_lines.append("")
    
    md_path = output_path / 'evaluation_report.md'
    with open(md_path, 'w') as f:
        f.write('\n'.join(md_lines))
    
    print(f"\nReports saved to:")
    print(f"  - {json_path}")
    print(f"  - {md_path}")


def main():
    parser = argparse.ArgumentParser(description='Multi-model evaluation for LongListBench')
    parser.add_argument('--models', nargs='+', default=['gemini', 'gpt4', 'claude'],
                       choices=['gemini', 'gpt4', 'claude'],
                       help='Models to evaluate (default: all)')
    parser.add_argument('--tiers', nargs='+', default=None,
                       choices=['easy', 'medium', 'hard', 'extreme'],
                       help='Difficulty tiers to test (default: all)')
    parser.add_argument('--formats', nargs='+', default=None,
                       choices=['detailed', 'table'],
                       help='Document formats to test (default: all)')
    parser.add_argument('--samples', nargs='+', default=None,
                       help='Specific samples to test (default: all available)')
    parser.add_argument('--quick', action='store_true',
                       help='Quick test with one sample per tier')
    
    args = parser.parse_args()
    
    # Quick mode: one sample per tier
    if args.quick:
        args.samples = [
            'easy_10_001_detailed',
            'medium_25_001_detailed',
            'hard_50_001_detailed',
        ]
    
    print("="*70)
    print("MULTI-MODEL EVALUATION: LongListBench Benchmark")
    print("="*70)
    print()
    print(f"Models: {', '.join(args.models)}")
    print(f"Tiers: {args.tiers or 'all'}")
    print(f"Formats: {args.formats or 'all'}")
    print()
    
    results = run_evaluation(
        models=args.models,
        samples=args.samples,
        tiers=args.tiers,
        formats=args.formats,
    )
    
    # Generate reports
    output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(exist_ok=True)
    generate_report(results, output_dir)
    
    print()
    print("="*70)
    print("EVALUATION COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
