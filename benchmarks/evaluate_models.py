#!/usr/bin/env python3
"""Multi-model evaluation script for the LongListBench benchmark.

Runs extraction tests on GPT-4o, GPT-5.2, and Gemini 2.5 using the same prompts.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

_SCRIPT_DIR = Path(__file__).parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from models.loss_run import FinancialBreakdown, LossRunIncident

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

try:
    from tenacity import RetryError, retry, stop_after_attempt, wait_exponential
except ModuleNotFoundError:
    RetryError = None
    def retry(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    def stop_after_attempt(*args, **kwargs):
        return None

    def wait_exponential(*args, **kwargs):
        return None


if load_dotenv is not None:
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    load_dotenv(_REPO_ROOT / ".env")
    load_dotenv(Path(__file__).parent / ".env")

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
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in environment")
    import google.genai as genai
    return genai.Client(api_key=api_key)


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

class LossRunExtraction(BaseModel):
    incidents: list[LossRunIncident]


_LOSS_RUN_FIELDS = set(LossRunIncident.model_fields.keys())
_BREAKDOWN_FIELDS = set(FinancialBreakdown.model_fields.keys())
_BREAKDOWN_KEYS = {"bi", "pd", "lae", "ded"}

_LOSS_RUN_EXTRACTION_SCHEMA_JSON = json.dumps(
    LossRunExtraction.model_json_schema(),
    indent=2,
    ensure_ascii=False,
)


EXTRACTION_PROMPT = """Extract all incident records from the following document.

Requirements:
- Return ALL incidents you can find in the document.
- Each incident MUST include ALL fields in the schema.
- When a value is unknown:
  - For required string fields, use "" (empty string), not null.
  - For optional fields, use null.
  - For list fields, use [].
  - For numeric fields, use 0.0.
- Output MUST be valid JSON that conforms to the schema.

Schema (JSON Schema):
{schema_json}

Output JSON shape:
{{
  "incidents": [ ... ]
}}

Document:
{ocr_text}
"""


def parse_json_response(response_text: str) -> Any:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = response_text.strip()

    code_block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if code_block_match is not None:
        text = code_block_match.group(1).strip()

    def _repair_common_json_issues(s: str) -> str:
        s = s.strip()
        s = re.sub(r",\s*([}\]])", r"\1", s)
        s = re.sub(r"}\s*{", r"},{", s)
        s = re.sub(r"\]\s*\[", r"],[", s)
        s = re.sub(r'"\s*(?="[^"]*"\s*:)', '",', s)
        s = re.sub(r'\b(true|false|null)\b\s*(?="[^"]*"\s*:)', r"\1,", s)
        s = re.sub(r'(\d+(?:\.\d+)?|\]|\})\s*(?="[^"]*"\s*:)', r"\1,", s)
        return s

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start_candidates = [p for p in (text.find('{'), text.find('[')) if p != -1]
        if not start_candidates:
            raise
        start = min(start_candidates)
        end_obj = text.rfind('}')
        end_arr = text.rfind(']')
        end = max(end_obj, end_arr)
        if end <= start:
            raise

        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            repaired = _repair_common_json_issues(candidate)
            return json.loads(repaired)


def _validate_incident_dict_is_complete(incident: dict) -> None:
    extra = set(incident.keys()) - _LOSS_RUN_FIELDS
    if extra:
        raise ValueError(f"Incident has unexpected fields: {sorted(extra)}")

    missing = _LOSS_RUN_FIELDS - set(incident.keys())
    if missing:
        raise ValueError(f"Incident missing required fields: {sorted(missing)}")

    for breakdown_key in _BREAKDOWN_KEYS:
        if breakdown_key not in incident:
            raise ValueError(f"Incident missing required field: {breakdown_key}")
        breakdown = incident.get(breakdown_key)
        if not isinstance(breakdown, dict):
            raise ValueError(f"Incident field '{breakdown_key}' must be an object")

        b_extra = set(breakdown.keys()) - _BREAKDOWN_FIELDS
        if b_extra:
            raise ValueError(
                f"Incident.{breakdown_key} has unexpected fields: {sorted(b_extra)}"
            )

        b_missing = _BREAKDOWN_FIELDS - set(breakdown.keys())
        if b_missing:
            raise ValueError(
                f"Incident.{breakdown_key} missing required fields: {sorted(b_missing)}"
            )


def _validate_and_normalize_predictions(raw: object) -> list[dict]:
    if isinstance(raw, BaseModel):
        raw = raw.model_dump(mode="json")

    incidents: object
    if isinstance(raw, dict):
        if "incidents" not in raw:
            raise ValueError("Model output must include key 'incidents' (list)")
        extra_top_level = set(raw.keys()) - {"incidents"}
        if extra_top_level:
            raise ValueError(
                f"Model output has unexpected top-level keys: {sorted(extra_top_level)}"
            )
        incidents = raw.get("incidents")
    elif isinstance(raw, list):
        incidents = raw
    else:
        raise ValueError("Model output must be either a list of incidents or an object with key 'incidents'")

    if not isinstance(incidents, list):
        raise ValueError("Model output 'incidents' must be a list")

    normalized: list[dict] = []
    for idx, item in enumerate(incidents):
        if not isinstance(item, dict):
            raise ValueError(f"Incident at index {idx} must be an object")
        _validate_incident_dict_is_complete(item)
        try:
            model_obj = LossRunIncident.model_validate(item)
        except ValidationError as e:
            raise ValueError(f"Incident at index {idx} failed schema validation: {e}") from e
        normalized.append(model_obj.model_dump(mode="json"))

    return normalized


_INCIDENT_MARKER_RE = re.compile(r"(?:Incident\s*#\s*\d{5}|#\d{5})")
_MAX_INCIDENTS_PER_CHUNK = 8


def _split_ocr_into_chunks(
    ocr_text: str,
    *,
    max_incidents_per_chunk: int = _MAX_INCIDENTS_PER_CHUNK,
    max_chunk_chars: int = 60000,
    overlap_chars: int = 1200,
) -> list[str]:
    markers = [m.start() for m in _INCIDENT_MARKER_RE.finditer(ocr_text)]
    if not markers:
        chunks: list[str] = []
        start = 0
        while start < len(ocr_text):
            end = min(len(ocr_text), start + max_chunk_chars)
            chunks.append(ocr_text[start:end])
            if end >= len(ocr_text):
                break
            start = max(0, end - overlap_chars)
        return chunks

    chunks = []
    start = max(0, markers[0] - overlap_chars)
    incident_count = 0
    for idx, pos in enumerate(markers):
        incident_count += 1
        next_pos = markers[idx + 1] if idx + 1 < len(markers) else len(ocr_text)

        too_many_incidents = incident_count >= max_incidents_per_chunk
        too_many_chars = (next_pos - start) >= max_chunk_chars
        is_last = idx == len(markers) - 1

        if too_many_incidents or too_many_chars or is_last:
            end = next_pos
            end = min(len(ocr_text), end + overlap_chars)
            chunks.append(ocr_text[start:end])
            start = max(0, next_pos - overlap_chars)
            incident_count = 0

    return chunks


def _merge_incident_records(existing: dict, incoming: dict) -> dict:
    merged = dict(existing)
    for k, v in incoming.items():
        if k in _BREAKDOWN_KEYS and isinstance(v, dict) and isinstance(merged.get(k), dict):
            b = dict(merged[k])
            for bk, bv in v.items():
                if (b.get(bk) in (0, 0.0) or b.get(bk) is None) and bv not in (0, 0.0, None):
                    b[bk] = bv
            merged[k] = b
            continue

        cur = merged.get(k)
        if cur in (None, "", [], 0, 0.0):
            if v not in (None, "", [], 0, 0.0):
                merged[k] = v
    return merged


def _merge_incident_lists(incidents: list[list[dict]]) -> list[dict]:
    merged_by_id: dict[str, dict] = {}
    for chunk_list in incidents:
        for inc in chunk_list:
            inc_id = normalize_incident_number(inc.get("incident_number", ""))
            if not inc_id:
                continue
            if inc_id not in merged_by_id:
                merged_by_id[inc_id] = inc
            else:
                merged_by_id[inc_id] = _merge_incident_records(merged_by_id[inc_id], inc)

    merged = list(merged_by_id.values())
    merged.sort(key=lambda d: normalize_incident_number(d.get("incident_number", "")))
    return merged


def _should_chunk(ocr_text: str) -> bool:
    if len(ocr_text) >= 120000:
        return True
    return len(_INCIDENT_MARKER_RE.findall(ocr_text)) >= (2 * _MAX_INCIDENTS_PER_CHUNK)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=4, min=10, max=120))
def extract_with_gemini(client, ocr_text: str, model_id: str) -> list[dict]:
    """Extract claims using Gemini."""
    from google.genai import types

    def _extract_chunk(chunk_text: str) -> list[dict]:
        prompt = EXTRACTION_PROMPT.format(
            ocr_text=chunk_text,
            schema_json=_LOSS_RUN_EXTRACTION_SCHEMA_JSON,
        )
        # Disable thinking for Gemini 2.5+ models to avoid token consumption
        # that truncates JSON output
        thinking_config = None
        if "2.5" in model_id or "3" in model_id.split("-")[0]:
            thinking_config = types.ThinkingConfig(thinking_budget=0)
        
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                maxOutputTokens=8192,
                responseMimeType="application/json",
                responseSchema=LossRunExtraction,
                thinking_config=thinking_config,
            ),
        )
        parsed = getattr(response, "parsed", None)
        raw = parsed if parsed is not None else parse_json_response(response.text)
        return _validate_and_normalize_predictions(raw)

    if not _should_chunk(ocr_text):
        return _extract_chunk(ocr_text)

    chunks = _split_ocr_into_chunks(ocr_text)
    max_workers = int(os.getenv("LLB_GEMINI_CHUNK_WORKERS", "2"))
    per_chunk: list[list[dict]] = [None] * len(chunks)
    if max_workers <= 1 or len(chunks) <= 1:
        for i, chunk in enumerate(chunks):
            per_chunk[i] = _extract_chunk(chunk)
    else:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(chunks))) as ex:
            futures = [ex.submit(_extract_chunk, chunk) for chunk in chunks]
            for i, fut in enumerate(futures):
                per_chunk[i] = fut.result()
    return _merge_incident_lists(per_chunk)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=60))
def extract_with_openai(client, ocr_text: str, model_id: str) -> list[dict]:
    """Extract claims using OpenAI."""

    def _extract_chunk(chunk_text: str) -> list[dict]:
        prompt = EXTRACTION_PROMPT.format(
            ocr_text=chunk_text,
            schema_json=_LOSS_RUN_EXTRACTION_SCHEMA_JSON,
        )
        try:
            response = client.beta.chat.completions.parse(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_completion_tokens=8192,
                response_format=LossRunExtraction,
            )
            parsed = getattr(response.choices[0].message, "parsed", None)
            if parsed is not None:
                raw = parsed
            else:
                raw = parse_json_response(response.choices[0].message.content)
        except Exception:
            # Some models do not support the structured parse endpoint; fall back to JSON mode.
            response = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_completion_tokens=8192,
                response_format={"type": "json_object"},
            )
            raw = parse_json_response(response.choices[0].message.content)
        return _validate_and_normalize_predictions(raw)

    if not _should_chunk(ocr_text):
        return _extract_chunk(ocr_text)

    chunks = _split_ocr_into_chunks(ocr_text)
    max_workers = int(os.getenv("LLB_OPENAI_CHUNK_WORKERS", "4"))
    per_chunk: list[list[dict]] = [None] * len(chunks)
    if max_workers <= 1 or len(chunks) <= 1:
        for i, chunk in enumerate(chunks):
            per_chunk[i] = _extract_chunk(chunk)
    else:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(chunks))) as ex:
            futures = [ex.submit(_extract_chunk, chunk) for chunk in chunks]
            for i, fut in enumerate(futures):
                per_chunk[i] = fut.result()
    return _merge_incident_lists(per_chunk)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=60))
def extract_with_anthropic(client, ocr_text: str, model_id: str) -> list[dict]:
    """Extract claims using Anthropic Claude."""

    def _extract_chunk(chunk_text: str) -> list[dict]:
        prompt = EXTRACTION_PROMPT.format(
            ocr_text=chunk_text,
            schema_json=_LOSS_RUN_EXTRACTION_SCHEMA_JSON,
        )
        response = client.messages.create(
            model=model_id,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = parse_json_response(response.content[0].text)
        return _validate_and_normalize_predictions(raw)

    if not _should_chunk(ocr_text):
        return _extract_chunk(ocr_text)

    chunks = _split_ocr_into_chunks(ocr_text)
    max_workers = int(os.getenv("LLB_ANTHROPIC_CHUNK_WORKERS", "2"))
    per_chunk: list[list[dict]] = [None] * len(chunks)
    if max_workers <= 1 or len(chunks) <= 1:
        for i, chunk in enumerate(chunks):
            per_chunk[i] = _extract_chunk(chunk)
    else:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(chunks))) as ex:
            futures = [ex.submit(_extract_chunk, chunk) for chunk in chunks]
            for i, fut in enumerate(futures):
                per_chunk[i] = fut.result()
    return _merge_incident_lists(per_chunk)


# Model configurations
MODELS = {
    'gemini': ModelConfig(
        name='Gemini 2.5',
        provider='Google',
        model_id=os.getenv('GEMINI_MODEL_ID', 'gemini-2.5-flash'),
        setup_fn=setup_gemini,
        extract_fn=extract_with_gemini,
    ),
    # Alias for backwards compatibility
    'gemini25': ModelConfig(
        name='Gemini 2.5',
        provider='Google',
        model_id=os.getenv('GEMINI_25_MODEL_ID', 'gemini-2.5-flash'),
        setup_fn=setup_gemini,
        extract_fn=extract_with_gemini,
    ),
    'gpt52': ModelConfig(
        name='GPT-5.2',
        provider='OpenAI',
        model_id='gpt-5.2',
        setup_fn=setup_openai,
        extract_fn=extract_with_openai,
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

    _OPTIONAL_STR_FIELDS = {
        "cause_code",
        "unit_number",
        "agency",
        "driver_name",
        "adjuster_notes",
    }
    _BREAKDOWN_KEYS = {"bi", "pd", "lae", "ded"}
    _BREAKDOWN_FIELDS = {"reserve", "paid", "recovered", "total_incurred"}

    def _norm_str(v: Any, *, optional: bool) -> Any:
        if v is None:
            return None
        s = str(v).strip()
        if optional and s == "":
            return None
        return s

    def _norm_float(v: Any) -> float:
        try:
            f = float(v)
        except Exception:
            f = 0.0
        f = round(f, 2)
        if f == -0.0:
            f = 0.0
        return f

    def _canonicalize(item: dict) -> dict:
        obj = LossRunIncident.model_validate(item).model_dump(mode="json")

        for k, v in list(obj.items()):
            if k in _BREAKDOWN_KEYS:
                if not isinstance(v, dict):
                    v = {}
                b: dict[str, Any] = {}
                for bf in _BREAKDOWN_FIELDS:
                    b[bf] = _norm_float(v.get(bf, 0.0))
                obj[k] = b
            elif k == "claimants":
                if not isinstance(v, list):
                    v = []
                cleaned = [str(x).strip() for x in v if str(x).strip()]
                obj[k] = sorted(cleaned)
            elif isinstance(v, str) or v is None:
                obj[k] = _norm_str(v, optional=(k in _OPTIONAL_STR_FIELDS))
            else:
                obj[k] = v

        return obj

    def _flatten_pairs(incident_id: str, obj: dict) -> list[str]:
        pairs: list[str] = []
        for k, v in obj.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    pairs.append(
                        json.dumps(
                            [incident_id, f"{k}.{kk}", vv],
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    )
            else:
                pairs.append(
                    json.dumps(
                        [incident_id, k, v],
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
        return pairs

    gt_by_id: dict[str, list[str]] = {}
    pred_by_id: dict[str, list[str]] = {}

    gt_pairs: list[str] = []
    pred_pairs: list[str] = []

    for item in ground_truth:
        obj = _canonicalize(item)
        inc = normalize_incident_number(obj.get("incident_number", ""))
        gt_by_id.setdefault(inc, []).append(json.dumps(obj, sort_keys=True, separators=(",", ":")))
        gt_pairs.extend(_flatten_pairs(inc, obj))

    for item in predicted:
        obj = _canonicalize(item)
        inc = normalize_incident_number(obj.get("incident_number", ""))
        pred_by_id.setdefault(inc, []).append(json.dumps(obj, sort_keys=True, separators=(",", ":")))
        pred_pairs.extend(_flatten_pairs(inc, obj))

    gt_ids = set(gt_by_id.keys()) - {""}
    pred_ids = set(pred_by_id.keys()) - {""}

    missing_ids = sorted(gt_ids - pred_ids)
    extra_ids = sorted(pred_ids - gt_ids)

    exact_record_matches = 0
    for inc in sorted(gt_ids & pred_ids):
        exact_record_matches += sum((Counter(gt_by_id.get(inc, [])) & Counter(pred_by_id.get(inc, []))).values())

    gt_pairs_counter = Counter(gt_pairs)
    pred_pairs_counter = Counter(pred_pairs)
    found_pairs = sum((gt_pairs_counter & pred_pairs_counter).values())

    total_gt_pairs = sum(gt_pairs_counter.values())
    total_pred_pairs = sum(pred_pairs_counter.values())

    recall = found_pairs / total_gt_pairs if total_gt_pairs > 0 else 0.0
    precision = found_pairs / total_pred_pairs if total_pred_pairs > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "ground_truth_count": gt_count,
        "predicted_count": pred_count,
        "found": found_pairs,
        "recall": recall,
        "precision": precision,
        "f1": f1,
        "missing": len(missing_ids),
        "extra": len(extra_ids),
        "missing_ids": missing_ids,
        "extra_ids": extra_ids,
        "exact_record_matches": exact_record_matches,
        "total_gold_field_pairs": total_gt_pairs,
        "total_pred_field_pairs": total_pred_pairs,
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
    parallel_models: bool = False,
    model_workers: int | None = None,
) -> list[EvaluationResult]:
    """Run evaluation across specified models and samples."""
    
    if claims_dir is None:
        claims_dir = Path(__file__).parent / "claims"
    if output_dir is None:
        output_dir = Path(__file__).parent / "results" / "scratch"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
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

    if not parallel_models:
        parallel_models = os.getenv("LLB_PARALLEL_MODELS", "0") == "1"

    if model_workers is None:
        model_workers = int(os.getenv("LLB_MODEL_WORKERS", str(len(models))))
    model_workers = max(1, int(model_workers))

    gemini_rate_lock = threading.Lock()
    gemini_next_allowed_time = 0.0

    def _gemini_rate_limit() -> None:
        nonlocal gemini_next_allowed_time
        with gemini_rate_lock:
            now = time.time()
            if now < gemini_next_allowed_time:
                time.sleep(gemini_next_allowed_time - now)
            gemini_next_allowed_time = time.time() + 5.0
    
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
        
        def _eval_one_model(model_key: str) -> EvaluationResult:
            config = MODELS[model_key]
            client = clients[model_key]

            if model_key.startswith("gemini"):
                _gemini_rate_limit()

            start_time = time.time()
            error = None
            predicted: list[dict] = []
            try:
                predicted = config.extract_fn(client, ocr_text, config.model_id)
            except Exception as e:
                if RetryError is not None and isinstance(e, RetryError) and getattr(e, "last_attempt", None) is not None:
                    underlying = e.last_attempt.exception()
                    error = f"{type(underlying).__name__}: {underlying}"
                else:
                    error = str(e)

            extraction_time = time.time() - start_time

            if not error:
                metrics = evaluate_extraction(predicted, ground_truth)
                pred_path = output_dir / f"{sample}_{model_key}_predicted.json"
                with open(pred_path, "w") as f:
                    json.dump(predicted, f, indent=2)
            else:
                metrics = {
                    "recall": 0,
                    "precision": 0,
                    "f1": 0,
                    "found": 0,
                    "ground_truth_count": len(ground_truth),
                    "predicted_count": 0,
                    "missing": len(ground_truth),
                    "extra": 0,
                }

            return EvaluationResult(
                model=model_key,
                sample=sample,
                tier=tier,
                format=fmt,
                metrics=metrics,
                extraction_time=extraction_time,
                error=error,
            )

        active_models = [m for m in models if m in clients]

        if not parallel_models or len(active_models) <= 1:
            for model_key in active_models:
                config = MODELS[model_key]
                print(f"  [{config.name}]")
                r = _eval_one_model(model_key)
                if r.error:
                    print(f"    ✗ Error: {r.error}")
                else:
                    m = r.metrics
                    print(f"    Predicted: {m['predicted_count']} claims")
                    print(f"    Recall: {m['recall']:.1%}  Precision: {m['precision']:.1%}  F1: {m['f1']:.1%}")
                    print(f"    Time: {r.extraction_time:.1f}s")
                    if m.get('missing', 0) > 0:
                        print(f"    ⚠ Missing: {m['missing']}")
                    if m.get('extra', 0) > 0:
                        print(f"    ⚠ Extra: {m['extra']}")
                results.append(r)
                print()
        else:
            with ThreadPoolExecutor(max_workers=min(model_workers, len(active_models))) as ex:
                future_map = {ex.submit(_eval_one_model, mk): mk for mk in active_models}
                for fut in as_completed(future_map):
                    r = fut.result()
                    config = MODELS[r.model]
                    print(f"  [{config.name}]")
                    if r.error:
                        print(f"    ✗ Error: {r.error}")
                    else:
                        m = r.metrics
                        print(f"    Predicted: {m['predicted_count']} claims")
                        print(f"    Recall: {m['recall']:.1%}  Precision: {m['precision']:.1%}  F1: {m['f1']:.1%}")
                        print(f"    Time: {r.extraction_time:.1f}s")
                        if m.get('missing', 0) > 0:
                            print(f"    ⚠ Missing: {m['missing']}")
                        if m.get('extra', 0) > 0:
                            print(f"    ⚠ Extra: {m['extra']}")
                    results.append(r)
                    print()
        
        # Rate limiting between samples
        time.sleep(1)
    
    return results


def run_evaluation_from_saved_predictions(
    models: list[str],
    samples: list[str] = None,
    tiers: list[str] = None,
    formats: list[str] = None,
    claims_dir: Path = None,
    output_dir: Path = None,
    previous_report_path: Path = None,
) -> list[EvaluationResult]:
    if claims_dir is None:
        claims_dir = Path(__file__).parent / "claims"
    if output_dir is None:
        output_dir = Path(__file__).parent / "results" / "scratch"

    output_dir.mkdir(parents=True, exist_ok=True)

    if samples is None:
        samples = []
        for ocr_file in sorted(claims_dir.glob("*_ocr.md")):
            sample = ocr_file.stem.replace("_ocr", "")
            json_file = claims_dir / f"{sample}.json"
            if json_file.exists() and ocr_file.stat().st_size > 0:
                tier, fmt = get_sample_info(sample)
                if (tiers is None or tier in tiers) and (formats is None or fmt in formats):
                    samples.append(sample)

    time_lookup: dict[tuple[str, str], float] = {}

    report_paths: list[Path] = []
    current_report_path = output_dir / "evaluation_report.json"
    report_paths.append(current_report_path)
    if previous_report_path is not None:
        try:
            if previous_report_path.resolve() != current_report_path.resolve():
                report_paths.append(previous_report_path)
        except Exception:
            report_paths.append(previous_report_path)

    for report_path in report_paths:
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                for entry in report.get("detailed_results", []):
                    if entry.get("error"):
                        continue
                    key = (entry.get("sample"), entry.get("model"))
                    if not key[0] or not key[1] or entry.get("extraction_time") is None:
                        continue
                    t = float(entry["extraction_time"])
                    if t > 0 and time_lookup.get(key, 0.0) == 0.0:
                        time_lookup[key] = t
            except Exception:
                pass

    try:
        repo_root = Path(__file__).resolve().parent.parent
        rel_report_path = current_report_path.resolve().relative_to(repo_root)
        head_json = subprocess.check_output(
            [
                "git",
                "-C",
                str(repo_root),
                "show",
                f"HEAD:{rel_report_path.as_posix()}",
            ],
            text=True,
        )
        head_report = json.loads(head_json)
        for entry in head_report.get("detailed_results", []):
            if entry.get("error"):
                continue
            key = (entry.get("sample"), entry.get("model"))
            if key[0] and key[1] and entry.get("extraction_time") is not None:
                t = float(entry["extraction_time"])
                if t > 0 and time_lookup.get(key, 0.0) == 0.0:
                    time_lookup[key] = t
    except Exception:
        pass

    results: list[EvaluationResult] = []

    for sample in samples:
        tier, fmt = get_sample_info(sample)
        json_path = claims_dir / f"{sample}.json"
        with open(json_path) as f:
            ground_truth = json.load(f)

        for model_key in models:
            if model_key not in MODELS:
                continue

            pred_path = output_dir / f"{sample}_{model_key}_predicted.json"
            error = None
            predicted: list[dict] = []
            if pred_path.exists():
                try:
                    raw_predicted = json.loads(pred_path.read_text(encoding="utf-8"))
                    predicted = _validate_and_normalize_predictions(raw_predicted)
                except Exception as e:
                    error = f"Failed to load predicted JSON: {e}"
            else:
                error = f"Missing predicted file: {pred_path.name}"

            if not error:
                metrics = evaluate_extraction(predicted, ground_truth)
            else:
                metrics = {
                    "recall": 0,
                    "precision": 0,
                    "f1": 0,
                    "found": 0,
                    "ground_truth_count": len(ground_truth),
                    "predicted_count": 0,
                    "missing": len(ground_truth),
                    "extra": 0,
                }

            extraction_time = time_lookup.get((sample, model_key), 0.0)

            results.append(
                EvaluationResult(
                    model=model_key,
                    sample=sample,
                    tier=tier,
                    format=fmt,
                    metrics=metrics,
                    extraction_time=extraction_time,
                    error=error,
                )
            )

    return results


def generate_report(results: list[EvaluationResult], output_path: Path):
    """Generate summary report in JSON and Markdown formats."""

    model_order: list[str] = []
    for r in results:
        if r.model not in model_order:
            model_order.append(r.model)
    
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
    
    for model_key in model_order:
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
    
    for model_key in model_order:
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
    
    for model_key in model_order:
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
    parser.add_argument('--models', nargs='+', default=['gemini', 'gpt4', 'gpt52'],
                       choices=['gemini', 'gemini25', 'gpt52', 'gpt4', 'claude'],
                       help='Models to evaluate (default: gemini, gpt4, gpt52)')
    parser.add_argument('--output-dir', default=None,
                       help='Directory to write predictions and evaluation reports (default: benchmarks/results/scratch)')
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
    parser.add_argument('--offline', action='store_true',
                       help='Regenerate reports from saved *_predicted.json files (no API calls)')
    parser.add_argument('--previous-report', default=None,
                       help='Optional path to an evaluation_report.json to reuse extraction_time values from')
    parser.add_argument('--parallel-models', action='store_true',
                       help='Run all selected models in parallel for each sample')
    parser.add_argument('--model-workers', type=int, default=None,
                       help='Max number of parallel model workers (default: len(models) or LLB_MODEL_WORKERS)')
    
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
    
    if args.offline: 
        previous_report_path = Path(args.previous_report) if args.previous_report else None
        output_dir = Path(args.output_dir) if args.output_dir else (Path(__file__).parent / "results" / "scratch")
        results = run_evaluation_from_saved_predictions(
            models=args.models,
            samples=args.samples,
            tiers=args.tiers,
            formats=args.formats,
            output_dir=output_dir,
            previous_report_path=previous_report_path,
        )
    else:
        output_dir = Path(args.output_dir) if args.output_dir else (Path(__file__).parent / "results" / "scratch")
        results = run_evaluation(
            models=args.models,
            samples=args.samples,
            tiers=args.tiers,
            formats=args.formats,
            output_dir=output_dir,
            parallel_models=args.parallel_models,
            model_workers=args.model_workers,
        )
    
    # Generate reports
    generate_report(results, output_dir)
    
    print()
    print("="*70)
    print("EVALUATION COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
