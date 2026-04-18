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
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
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
    from .evaluation_metrics import evaluate_extraction
except ImportError:
    from evaluation_metrics import evaluate_extraction

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


def _repair_truncated_json(raw: str) -> dict | None:
    """Salvage complete incidents from truncated JSON output.

    When the LLM hits the output-token limit the JSON is cut mid-object.
    This helper finds the last complete incident object in the array and
    returns a valid partial result.
    """
    idx = raw.find('"incidents"')
    if idx == -1:
        return None
    arr_start = raw.find("[", idx)
    if arr_start == -1:
        return None

    # Walk the array region tracking brace depth while respecting JSON strings
    # so that braces inside string values (e.g. descriptions) are ignored.
    search_region = raw[arr_start:]
    last_good = -1
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(search_region):
        if escape:
            escape = False
            continue
        if ch == "\\":
            if in_string:
                escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                last_good = i
    if last_good == -1:
        return None

    repaired = '{"incidents": ' + search_region[: last_good + 1] + "]}"
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


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
            try:
                repaired = _repair_common_json_issues(candidate)
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass

        # Last resort: salvage complete incidents from truncated JSON
        salvaged = _repair_truncated_json(text)
        if salvaged is not None:
            return salvaged
        raise json.JSONDecodeError("Could not parse JSON response", text, 0)


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


_DEFAULT_GEMINI_CHUNK_MAX_INPUT_TOKENS = 12000


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=2, max=30))
def _count_gemini_tokens(client, model_id: str, text: str) -> int:
    response = client.models.count_tokens(model=model_id, contents=text)
    total_tokens = getattr(response, "total_tokens", None)
    if total_tokens is None:
        raise ValueError("Gemini count_tokens response did not include total_tokens")
    return int(total_tokens)


def _split_ocr_into_token_chunks(
    client,
    model_id: str,
    ocr_text: str,
    *,
    max_chunk_tokens: int,
) -> list[str]:
    if not ocr_text:
        return []

    chunks: list[str] = []
    start = 0
    text_len = len(ocr_text)
    while start < text_len:
        lo = start + 1
        hi = text_len
        best_end = start + 1

        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = ocr_text[start:mid]
            if _count_gemini_tokens(client, model_id, candidate) <= max_chunk_tokens:
                best_end = mid
                lo = mid + 1
            else:
                hi = mid - 1

        chunks.append(ocr_text[start:best_end])
        start = best_end

    return chunks


def _split_text_into_char_chunks(
    text: str,
    *,
    max_chunk_chars: int = 60000,
) -> list[str]:
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(text_len, start + max_chunk_chars)
        chunks.append(text[start:end])
        start = end
    return chunks


def _should_chunk_by_chars(text: str, *, max_chunk_chars: int = 60000) -> bool:
    return len(text) > max_chunk_chars


def _concatenate_incident_lists(incidents: list[list[dict]]) -> list[dict]:
    combined: list[dict] = []
    for chunk_list in incidents:
        combined.extend(chunk_list)
    return combined


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=4, min=10, max=120))
def extract_with_gemini(client, ocr_text: str, model_id: str) -> list[dict]:
    """Extract claims using Gemini."""
    return _extract_with_gemini_mode(client, ocr_text, model_id, allow_chunking=True, structured_output=True)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=4, min=10, max=120))
def extract_with_gemini_oneshot(client, ocr_text: str, model_id: str) -> list[dict]:
    """Extract claims using Gemini in full-context one-shot mode."""
    return _extract_with_gemini_mode(client, ocr_text, model_id, allow_chunking=False, structured_output=False)


def _extract_with_gemini_mode(
    client,
    ocr_text: str,
    model_id: str,
    *,
    allow_chunking: bool,
    structured_output: bool,
) -> list[dict]:
    from google.genai import types

    def _extract_chunk(chunk_text: str) -> list[dict]:
        prompt = EXTRACTION_PROMPT.format(
            ocr_text=chunk_text,
            schema_json=_LOSS_RUN_EXTRACTION_SCHEMA_JSON,
        )
        thinking_config = None
        if "flash" in model_id:
            thinking_config = types.ThinkingConfig(thinking_budget=0)

        config_kwargs = {
            "temperature": 0,
            "maxOutputTokens": 8192,
            "thinking_config": thinking_config,
        }
        if structured_output:
            config_kwargs["responseMimeType"] = "application/json"
            config_kwargs["responseSchema"] = LossRunExtraction

        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        if structured_output:
            parsed = getattr(response, "parsed", None)
            raw = parsed if parsed is not None else parse_json_response(response.text)
        else:
            raw = parse_json_response(response.text)
        return _validate_and_normalize_predictions(raw)

    if not allow_chunking:
        return _extract_chunk(ocr_text)

    max_chunk_tokens = int(
        os.getenv("LLB_GEMINI_CHUNK_MAX_INPUT_TOKENS", str(_DEFAULT_GEMINI_CHUNK_MAX_INPUT_TOKENS))
    )
    if _count_gemini_tokens(client, model_id, ocr_text) <= max_chunk_tokens:
        return _extract_chunk(ocr_text)

    chunks = _split_ocr_into_token_chunks(
        client,
        model_id,
        ocr_text,
        max_chunk_tokens=max_chunk_tokens,
    )
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
    return _concatenate_incident_lists(per_chunk)


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

    if not _should_chunk_by_chars(ocr_text):
        return _extract_chunk(ocr_text)

    chunks = _split_text_into_char_chunks(ocr_text)
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
    return _concatenate_incident_lists(per_chunk)


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

    if not _should_chunk_by_chars(ocr_text):
        return _extract_chunk(ocr_text)

    chunks = _split_text_into_char_chunks(ocr_text)
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
    return _concatenate_incident_lists(per_chunk)


# Model configurations
MODELS = {
    'gemini': ModelConfig(
        name='Gemini 2.5',
        provider='Google',
        model_id=os.getenv('GEMINI_MODEL_ID', 'gemini-2.5-flash'),
        setup_fn=setup_gemini,
        extract_fn=extract_with_gemini,
    ),
    'gemini_oneshot': ModelConfig(
        name='Gemini 2.5 (One-shot)',
        provider='Google',
        model_id=os.getenv('GEMINI_ONESHOT_MODEL_ID', os.getenv('GEMINI_MODEL_ID', 'gemini-2.5-flash')),
        setup_fn=setup_gemini,
        extract_fn=extract_with_gemini_oneshot,
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
    transcript: str = "ocr"


_TRANSCRIPT_SUFFIXES = {
    "ocr": "_ocr.md",
    "canonical": "_canonical.md",
}

_QUICK_SAMPLES = [
    "easy_10_001_detailed",
    "medium_25_001_detailed",
    "hard_50_001_detailed",
    "extreme_100_001_detailed",
]


@dataclass(frozen=True)
class EvaluationInput:
    sample: str
    tier: str
    format: str
    transcript: str


def _transcript_input_path(claims_dir: Path, sample: str, transcript: str) -> Path:
    return claims_dir / f"{sample}{_TRANSCRIPT_SUFFIXES[transcript]}"


def _prediction_output_path(output_dir: Path, sample: str, transcript: str, model_key: str) -> Path:
    return output_dir / f"{sample}_{transcript}_{model_key}_predicted.json"


def _legacy_prediction_output_path(output_dir: Path, sample: str, transcript: str, model_key: str) -> Path | None:
    if transcript != "ocr":
        return None
    return output_dir / f"{sample}_{model_key}_predicted.json"


def _discover_evaluation_inputs(
    *,
    claims_dir: Path,
    samples: list[str] | None,
    tiers: list[str] | None,
    formats: list[str] | None,
    transcripts: list[str] | None,
) -> list[EvaluationInput]:
    transcript_list = transcripts or ["ocr"]
    out: list[EvaluationInput] = []

    if samples is None:
        sample_names = set()
        for transcript in transcript_list:
            suffix = _TRANSCRIPT_SUFFIXES[transcript]
            for transcript_path in claims_dir.glob(f"*{suffix}"):
                if transcript_path.stat().st_size <= 0:
                    continue
                sample = transcript_path.name[: -len(suffix)]
                json_file = claims_dir / f"{sample}.json"
                if not json_file.exists():
                    continue
                tier, fmt = get_sample_info(sample)
                if (tiers is None or tier in tiers) and (formats is None or fmt in formats):
                    sample_names.add(sample)
        ordered_samples = sorted(sample_names)
    else:
        ordered_samples = list(samples)

    for sample in ordered_samples:
        tier, fmt = get_sample_info(sample)
        if tiers is not None and tier not in tiers:
            continue
        if formats is not None and fmt not in formats:
            continue
        for transcript in transcript_list:
            transcript_path = _transcript_input_path(claims_dir, sample, transcript)
            json_file = claims_dir / f"{sample}.json"
            if transcript_path.exists() and transcript_path.stat().st_size > 0 and json_file.exists():
                out.append(EvaluationInput(sample=sample, tier=tier, format=fmt, transcript=transcript))

    return out


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
    transcripts: list[str] = None,
    claims_dir: Path = None,
    output_dir: Path = None,
    parallel_models: bool = False,
    model_workers: int | None = None,
    resume: bool = True,
) -> list[EvaluationResult]:
    """Run evaluation across specified models and samples."""
    
    if claims_dir is None:
        claims_dir = Path(__file__).parent / "claims"
    if output_dir is None:
        output_dir = Path(__file__).parent / "results" / "scratch"
    
    output_dir.mkdir(parents=True, exist_ok=True)

    eval_inputs = _discover_evaluation_inputs(
        claims_dir=claims_dir,
        samples=samples,
        tiers=tiers,
        formats=formats,
        transcripts=transcripts,
    )

    preview = [f"{entry.sample} ({entry.transcript})" for entry in eval_inputs[:5]]
    print(f"Evaluating {len(eval_inputs)} sample/transcript inputs across {len(models)} models")
    print(f"Samples: {', '.join(preview)}{'...' if len(eval_inputs) > 5 else ''}")
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

    active_models = [m for m in models if m in clients]
    total_pairs = len(eval_inputs) * len(active_models)
    if resume and total_pairs > 0:
        existing_pairs = 0
        for entry in eval_inputs:
            for model_key in active_models:
                pred_path = _prediction_output_path(output_dir, entry.sample, entry.transcript, model_key)
                legacy_path = _legacy_prediction_output_path(output_dir, entry.sample, entry.transcript, model_key)
                if pred_path.exists() and pred_path.stat().st_size > 0:
                    existing_pairs += 1
                elif legacy_path is not None and legacy_path.exists() and legacy_path.stat().st_size > 0:
                    existing_pairs += 1
        print(f"Resume enabled: {existing_pairs}/{total_pairs} prediction files already exist")
        print()

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
    
    pair_index = 0

    for sample_idx, entry in enumerate(eval_inputs, start=1):
        print(f"{'='*70}")
        print(f"Sample: {entry.sample} [{entry.transcript}] ({sample_idx}/{len(eval_inputs)})")
        print(f"{'='*70}")

        transcript_path = _transcript_input_path(claims_dir, entry.sample, entry.transcript)
        json_path = claims_dir / f"{entry.sample}.json"

        transcript_text = transcript_path.read_text(encoding='utf-8')
        with open(json_path) as f:
            ground_truth = json.load(f)
        
        print(f"  Ground truth: {len(ground_truth)} claims")
        print(f"  {entry.transcript} text: {len(transcript_text):,} characters")
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
                extract_timeout_s = float(os.getenv("LLB_EXTRACT_TIMEOUT_SECONDS", "1800"))
                heartbeat_s = float(os.getenv("LLB_EXTRACT_HEARTBEAT_SECONDS", "30"))

                def _do_extract() -> object:
                    return config.extract_fn(client, transcript_text, config.model_id)

                with ThreadPoolExecutor(max_workers=1) as _ex:
                    _fut = _ex.submit(_do_extract)
                    raw_predicted: object
                    while True:
                        remaining = extract_timeout_s - (time.time() - start_time)
                        if remaining <= 0:
                            raise FuturesTimeoutError()
                        try:
                            raw_predicted = _fut.result(timeout=min(heartbeat_s, remaining))
                            break
                        except FuturesTimeoutError:
                            elapsed = time.time() - start_time
                            print(
                                f"    … still extracting ({elapsed:.0f}s/{extract_timeout_s:.0f}s)",
                                flush=True,
                            )
                predicted = _validate_and_normalize_predictions(raw_predicted)
            except FuturesTimeoutError:
                error = f"TimeoutError: extraction exceeded {os.getenv('LLB_EXTRACT_TIMEOUT_SECONDS', '1800')}s"
            except Exception as e:
                if RetryError is not None and isinstance(e, RetryError) and getattr(e, "last_attempt", None) is not None:
                    underlying = e.last_attempt.exception()
                    error = f"{type(underlying).__name__}: {underlying}"
                else:
                    error = str(e)

            extraction_time = time.time() - start_time

            if not error:
                metrics = evaluate_extraction(predicted, ground_truth)
                pred_path = _prediction_output_path(output_dir, entry.sample, entry.transcript, model_key)
                with open(pred_path, "w") as f:
                    json.dump(predicted, f, indent=2)
            else:
                metrics = evaluate_extraction([], ground_truth)

            return EvaluationResult(
                model=model_key,
                sample=entry.sample,
                tier=entry.tier,
                format=entry.format,
                metrics=metrics,
                extraction_time=extraction_time,
                error=error,
                transcript=entry.transcript,
            )

        if not parallel_models or len(active_models) <= 1:
            for model_key in active_models:
                pair_index += 1
                config = MODELS[model_key]
                pred_path = _prediction_output_path(output_dir, entry.sample, entry.transcript, model_key)
                legacy_path = _legacy_prediction_output_path(output_dir, entry.sample, entry.transcript, model_key)
                existing_pred_path = pred_path if pred_path.exists() and pred_path.stat().st_size > 0 else legacy_path
                if resume and existing_pred_path is not None and existing_pred_path.exists() and existing_pred_path.stat().st_size > 0:
                    try:
                        raw_predicted = json.loads(existing_pred_path.read_text(encoding="utf-8"))
                        predicted = _validate_and_normalize_predictions(raw_predicted)
                        metrics = evaluate_extraction(predicted, ground_truth)
                        r = EvaluationResult(
                            model=model_key,
                            sample=entry.sample,
                            tier=entry.tier,
                            format=entry.format,
                            metrics=metrics,
                            extraction_time=0.0,
                            error=None,
                            transcript=entry.transcript,
                        )
                        print(f"  [{config.name}] Pair {pair_index}/{total_pairs} SKIP")
                    except Exception as e:
                        print(f"  [{config.name}] Pair {pair_index}/{total_pairs} RUN (invalid existing prediction: {e})")
                        print(f"    → extracting…", flush=True)
                        r = _eval_one_model(model_key)
                else:
                    print(f"  [{config.name}] Pair {pair_index}/{total_pairs} RUN")
                    print(f"    → extracting…", flush=True)
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
                future_map = {}
                skipped: list[EvaluationResult] = []
                for model_key in active_models:
                    pair_index += 1
                    config = MODELS[model_key]
                    pred_path = _prediction_output_path(output_dir, entry.sample, entry.transcript, model_key)
                    legacy_path = _legacy_prediction_output_path(output_dir, entry.sample, entry.transcript, model_key)
                    existing_pred_path = pred_path if pred_path.exists() and pred_path.stat().st_size > 0 else legacy_path
                    if resume and existing_pred_path is not None and existing_pred_path.exists() and existing_pred_path.stat().st_size > 0:
                        try:
                            raw_predicted = json.loads(existing_pred_path.read_text(encoding="utf-8"))
                            predicted = _validate_and_normalize_predictions(raw_predicted)
                            metrics = evaluate_extraction(predicted, ground_truth)
                            skipped.append(
                                EvaluationResult(
                                    model=model_key,
                                    sample=entry.sample,
                                    tier=entry.tier,
                                    format=entry.format,
                                    metrics=metrics,
                                    extraction_time=0.0,
                                    error=None,
                                    transcript=entry.transcript,
                                )
                            )
                            print(f"  [{config.name}] Pair {pair_index}/{total_pairs} SKIP")
                        except Exception as e:
                            print(
                                f"  [{config.name}] Pair {pair_index}/{total_pairs} RUN (invalid existing prediction: {e})"
                            )
                            print(f"    → extracting…", flush=True)
                            future_map[ex.submit(_eval_one_model, model_key)] = model_key
                    else:
                        print(f"  [{config.name}] Pair {pair_index}/{total_pairs} RUN")
                        print(f"    → extracting…", flush=True)
                        future_map[ex.submit(_eval_one_model, model_key)] = model_key

                for r in skipped:
                    results.append(r)
                    m = r.metrics
                    config = MODELS[r.model]
                    print(f"  [{config.name}]")
                    print(f"    Predicted: {m['predicted_count']} claims")
                    print(f"    Recall: {m['recall']:.1%}  Precision: {m['precision']:.1%}  F1: {m['f1']:.1%}")
                    print(f"    Time: {r.extraction_time:.1f}s")
                    if m.get('missing', 0) > 0:
                        print(f"    ⚠ Missing: {m['missing']}")
                    if m.get('extra', 0) > 0:
                        print(f"    ⚠ Extra: {m['extra']}")
                    print()

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
    transcripts: list[str] = None,
    claims_dir: Path = None,
    output_dir: Path = None,
    previous_report_path: Path = None,
) -> list[EvaluationResult]:
    if claims_dir is None:
        claims_dir = Path(__file__).parent / "claims"
    if output_dir is None:
        output_dir = Path(__file__).parent / "results" / "scratch"

    output_dir.mkdir(parents=True, exist_ok=True)

    eval_inputs = _discover_evaluation_inputs(
        claims_dir=claims_dir,
        samples=samples,
        tiers=tiers,
        formats=formats,
        transcripts=transcripts,
    )

    time_lookup: dict[tuple[str, str, str], float] = {}

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
                    transcript = entry.get("transcript", "ocr")
                    key = (entry.get("sample"), transcript, entry.get("model"))
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
            transcript = entry.get("transcript", "ocr")
            key = (entry.get("sample"), transcript, entry.get("model"))
            if key[0] and key[2] and entry.get("extraction_time") is not None:
                t = float(entry["extraction_time"])
                if t > 0 and time_lookup.get(key, 0.0) == 0.0:
                    time_lookup[key] = t
    except Exception:
        pass

    results: list[EvaluationResult] = []

    for entry in eval_inputs:
        json_path = claims_dir / f"{entry.sample}.json"
        with open(json_path) as f:
            ground_truth = json.load(f)

        for model_key in models:
            if model_key not in MODELS:
                continue

            pred_path = _prediction_output_path(output_dir, entry.sample, entry.transcript, model_key)
            legacy_path = _legacy_prediction_output_path(output_dir, entry.sample, entry.transcript, model_key)
            existing_pred_path = pred_path if pred_path.exists() else legacy_path
            error = None
            predicted: list[dict] = []
            if existing_pred_path is not None and existing_pred_path.exists():
                try:
                    raw_predicted = json.loads(existing_pred_path.read_text(encoding="utf-8"))
                    predicted = _validate_and_normalize_predictions(raw_predicted)
                except Exception as e:
                    error = f"Failed to load predicted JSON: {e}"
            else:
                error = f"Missing predicted file: {pred_path.name}"

            if not error:
                metrics = evaluate_extraction(predicted, ground_truth)
            else:
                metrics = evaluate_extraction([], ground_truth)

            extraction_time = time_lookup.get((entry.sample, entry.transcript, model_key), 0.0)

            results.append(
                EvaluationResult(
                    model=model_key,
                    sample=entry.sample,
                    tier=entry.tier,
                    format=entry.format,
                    metrics=metrics,
                    extraction_time=extraction_time,
                    error=error,
                    transcript=entry.transcript,
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
                'total_found': 0,
                'total_gold_field_pairs': 0,
                'total_pred_field_pairs': 0,
                'total_rows': 0,
                'errors': 0,
                'by_tier': {},
                'by_format': {},
                'by_transcript': {},
            }
        
        stats = model_stats[r.model]
        stats['total_samples'] += 1
        stats['total_f1'] += r.metrics['f1']
        stats['total_recall'] += r.metrics['recall']
        stats['total_precision'] += r.metrics['precision']
        stats['total_found'] += r.metrics.get('found', 0)
        stats['total_gold_field_pairs'] += r.metrics.get('total_gold_field_pairs', 0)
        stats['total_pred_field_pairs'] += r.metrics.get('total_pred_field_pairs', 0)
        stats['total_rows'] += r.metrics.get('ground_truth_count', 0)
        if r.error:
            stats['errors'] += 1
        
        # By tier
        if r.tier not in stats['by_tier']:
            stats['by_tier'][r.tier] = {
                'count': 0,
                'rows': 0,
                'f1_sum': 0,
                'recall_sum': 0,
                'found_sum': 0,
                'gold_pairs_sum': 0,
                'pred_pairs_sum': 0,
            }
        stats['by_tier'][r.tier]['count'] += 1
        stats['by_tier'][r.tier]['rows'] += r.metrics.get('ground_truth_count', 0)
        stats['by_tier'][r.tier]['f1_sum'] += r.metrics['f1']
        stats['by_tier'][r.tier]['recall_sum'] += r.metrics['recall']
        stats['by_tier'][r.tier]['found_sum'] += r.metrics.get('found', 0)
        stats['by_tier'][r.tier]['gold_pairs_sum'] += r.metrics.get('total_gold_field_pairs', 0)
        stats['by_tier'][r.tier]['pred_pairs_sum'] += r.metrics.get('total_pred_field_pairs', 0)
        
        # By format
        if r.format not in stats['by_format']:
            stats['by_format'][r.format] = {
                'count': 0,
                'rows': 0,
                'f1_sum': 0,
                'recall_sum': 0,
                'found_sum': 0,
                'gold_pairs_sum': 0,
                'pred_pairs_sum': 0,
            }
        stats['by_format'][r.format]['count'] += 1
        stats['by_format'][r.format]['rows'] += r.metrics.get('ground_truth_count', 0)
        stats['by_format'][r.format]['f1_sum'] += r.metrics['f1']
        stats['by_format'][r.format]['recall_sum'] += r.metrics['recall']
        stats['by_format'][r.format]['found_sum'] += r.metrics.get('found', 0)
        stats['by_format'][r.format]['gold_pairs_sum'] += r.metrics.get('total_gold_field_pairs', 0)
        stats['by_format'][r.format]['pred_pairs_sum'] += r.metrics.get('total_pred_field_pairs', 0)

        # By transcript condition
        if r.transcript not in stats['by_transcript']:
            stats['by_transcript'][r.transcript] = {
                'count': 0,
                'rows': 0,
                'f1_sum': 0,
                'recall_sum': 0,
                'found_sum': 0,
                'gold_pairs_sum': 0,
                'pred_pairs_sum': 0,
            }
        stats['by_transcript'][r.transcript]['count'] += 1
        stats['by_transcript'][r.transcript]['rows'] += r.metrics.get('ground_truth_count', 0)
        stats['by_transcript'][r.transcript]['f1_sum'] += r.metrics['f1']
        stats['by_transcript'][r.transcript]['recall_sum'] += r.metrics['recall']
        stats['by_transcript'][r.transcript]['found_sum'] += r.metrics.get('found', 0)
        stats['by_transcript'][r.transcript]['gold_pairs_sum'] += r.metrics.get('total_gold_field_pairs', 0)
        stats['by_transcript'][r.transcript]['pred_pairs_sum'] += r.metrics.get('total_pred_field_pairs', 0)
    
    # Compute averages
    for model, stats in model_stats.items():
        n = stats['total_samples']
        stats['avg_f1'] = stats['total_f1'] / n if n > 0 else 0
        stats['avg_recall'] = stats['total_recall'] / n if n > 0 else 0
        stats['avg_precision'] = stats['total_precision'] / n if n > 0 else 0
        total_found = stats['total_found']
        total_gold = stats['total_gold_field_pairs']
        total_pred = stats['total_pred_field_pairs']
        stats['weighted_recall'] = total_found / total_gold if total_gold > 0 else 0
        stats['weighted_precision'] = total_found / total_pred if total_pred > 0 else 0
        stats['weighted_f1'] = (
            2 * stats['weighted_precision'] * stats['weighted_recall'] / (stats['weighted_precision'] + stats['weighted_recall'])
            if (stats['weighted_precision'] + stats['weighted_recall']) > 0 else 0
        )
        
        for tier_stats in stats['by_tier'].values():
            c = tier_stats['count']
            tier_stats['avg_f1'] = tier_stats['f1_sum'] / c if c > 0 else 0
            tier_stats['avg_recall'] = tier_stats['recall_sum'] / c if c > 0 else 0
            gold_pairs = tier_stats['gold_pairs_sum']
            pred_pairs = tier_stats['pred_pairs_sum']
            found_sum = tier_stats['found_sum']
            tier_stats['weighted_recall'] = found_sum / gold_pairs if gold_pairs > 0 else 0
            tier_stats['weighted_precision'] = found_sum / pred_pairs if pred_pairs > 0 else 0
            tier_stats['weighted_f1'] = (
                2 * tier_stats['weighted_precision'] * tier_stats['weighted_recall'] / (tier_stats['weighted_precision'] + tier_stats['weighted_recall'])
                if (tier_stats['weighted_precision'] + tier_stats['weighted_recall']) > 0 else 0
            )
        
        for fmt_stats in stats['by_format'].values():
            c = fmt_stats['count']
            fmt_stats['avg_f1'] = fmt_stats['f1_sum'] / c if c > 0 else 0
            fmt_stats['avg_recall'] = fmt_stats['recall_sum'] / c if c > 0 else 0
            gold_pairs = fmt_stats['gold_pairs_sum']
            pred_pairs = fmt_stats['pred_pairs_sum']
            found_sum = fmt_stats['found_sum']
            fmt_stats['weighted_recall'] = found_sum / gold_pairs if gold_pairs > 0 else 0
            fmt_stats['weighted_precision'] = found_sum / pred_pairs if pred_pairs > 0 else 0
            fmt_stats['weighted_f1'] = (
                2 * fmt_stats['weighted_precision'] * fmt_stats['weighted_recall'] / (fmt_stats['weighted_precision'] + fmt_stats['weighted_recall'])
                if (fmt_stats['weighted_precision'] + fmt_stats['weighted_recall']) > 0 else 0
            )

        for transcript_stats in stats['by_transcript'].values():
            c = transcript_stats['count']
            transcript_stats['avg_f1'] = transcript_stats['f1_sum'] / c if c > 0 else 0
            transcript_stats['avg_recall'] = transcript_stats['recall_sum'] / c if c > 0 else 0
            gold_pairs = transcript_stats['gold_pairs_sum']
            pred_pairs = transcript_stats['pred_pairs_sum']
            found_sum = transcript_stats['found_sum']
            transcript_stats['weighted_recall'] = found_sum / gold_pairs if gold_pairs > 0 else 0
            transcript_stats['weighted_precision'] = found_sum / pred_pairs if pred_pairs > 0 else 0
            transcript_stats['weighted_f1'] = (
                2 * transcript_stats['weighted_precision'] * transcript_stats['weighted_recall'] / (transcript_stats['weighted_precision'] + transcript_stats['weighted_recall'])
                if (transcript_stats['weighted_precision'] + transcript_stats['weighted_recall']) > 0 else 0
            )
    
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
                'transcript': r.transcript,
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
        "| Model | Weighted F1 | Weighted Recall | Weighted Precision | Macro F1 | Rows | Samples | Errors |",
        "|-------|-------------|-----------------|--------------------|----------|------|---------|--------|",
    ]

    def _format_weighted_pct(group_stats: dict | None) -> str:
        if not group_stats or group_stats.get("count", 0) == 0:
            return "N/A"
        return f"{group_stats['weighted_f1']:.1%}"
    
    for model_key in model_order:
        if model_key in model_stats:
            s = model_stats[model_key]
            name = MODELS[model_key].name
            md_lines.append(
                f"| {name} | {s['weighted_f1']:.1%} | {s['weighted_recall']:.1%} | "
                f"{s['weighted_precision']:.1%} | {s['avg_f1']:.1%} | {s['total_rows']} | {s['total_samples']} | {s['errors']} |"
            )
    
    md_lines.extend([
        "",
        "Primary scores use corpus-level micro aggregation over all field-value pairs, so larger incident lists contribute proportionally more evidence than smaller documents.",
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
                _format_weighted_pct(s["by_tier"].get(t)) for t in tiers
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
            detailed = _format_weighted_pct(s["by_format"].get("detailed"))
            table = _format_weighted_pct(s["by_format"].get("table"))
            md_lines.append(f"| {name} | {detailed} | {table} |")

    md_lines.extend([
        "",
        "## Results by Transcript Condition",
        "",
        "| Model | Canonical | OCR |",
        "|-------|-----------|-----|",
    ])

    for model_key in model_order:
        if model_key in model_stats:
            s = model_stats[model_key]
            name = MODELS[model_key].name
            canonical = _format_weighted_pct(s["by_transcript"].get("canonical"))
            ocr = _format_weighted_pct(s["by_transcript"].get("ocr"))
            md_lines.append(f"| {name} | {canonical} | {ocr} |")
    
    md_lines.extend([
        "",
        "## Detailed Results",
        "",
    ])
    
    # Group by sample
    samples_seen: set[tuple[str, str]] = set()
    for r in results:
        sample_key = (r.sample, r.transcript)
        if sample_key not in samples_seen:
            samples_seen.add(sample_key)
            md_lines.append(f"### {r.sample} ({r.transcript})")
            md_lines.append("")
            md_lines.append("| Model | F1 | Recall | Precision | Predicted | Time |")
            md_lines.append("|-------|-----|--------|-----------|-----------|------|")
            
            for r2 in results:
                if r2.sample == r.sample and r2.transcript == r.transcript:
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
    parser.add_argument('--models', nargs='+', default=['gemini', 'gpt52'],
                       choices=['gemini', 'gemini_oneshot', 'gemini25', 'gpt52', 'gpt4', 'claude'],
                       help='Models to evaluate (default: gemini, gpt52)')
    parser.add_argument('--output-dir', default=None,
                       help='Directory to write predictions and evaluation reports (default: benchmarks/results/scratch)')
    parser.add_argument('--tiers', nargs='+', default=None,
                       choices=['easy', 'medium', 'hard', 'extreme'],
                       help='Difficulty tiers to test (default: all)')
    parser.add_argument('--formats', nargs='+', default=None,
                       choices=['detailed', 'table'],
                       help='Document formats to test (default: all)')
    parser.add_argument('--transcripts', nargs='+', default=['ocr'],
                       choices=['canonical', 'ocr'],
                       help='Transcript conditions to test (default: ocr)')
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
    parser.add_argument('--no-resume', action='store_true',
                       help='Do not reuse existing *_predicted.json files; always rerun extractions')
    
    args = parser.parse_args()
    
    # Quick mode: one sample per tier
    if args.quick:
        args.samples = list(_QUICK_SAMPLES)
    
    print("="*70)
    print("MULTI-MODEL EVALUATION: LongListBench Benchmark")
    print("="*70)
    print()
    print(f"Models: {', '.join(args.models)}")
    print(f"Tiers: {args.tiers or 'all'}")
    print(f"Formats: {args.formats or 'all'}")
    print(f"Transcripts: {args.transcripts or 'all'}")
    print()
    
    if args.offline: 
        previous_report_path = Path(args.previous_report) if args.previous_report else None
        output_dir = Path(args.output_dir) if args.output_dir else (Path(__file__).parent / "results" / "scratch")
        results = run_evaluation_from_saved_predictions(
            models=args.models,
            samples=args.samples,
            tiers=args.tiers,
            formats=args.formats,
            transcripts=args.transcripts,
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
            transcripts=args.transcripts,
            output_dir=output_dir,
            parallel_models=args.parallel_models,
            model_workers=args.model_workers,
            resume=(not args.no_resume),
        )
    
    # Generate reports
    generate_report(results, output_dir)
    
    print()
    print("="*70)
    print("EVALUATION COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
