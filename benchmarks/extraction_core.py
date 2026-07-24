#!/usr/bin/env python3
"""Regime-agnostic extraction primitives shared across all extraction regimes.

Holds the loss-run schema, JSON parsing/repair, schema validation, the shared
extraction prompt, provider client setup, and the per-provider call engines
(Gemini mode engine + OpenAI single-call). The regime modules
(`regime_oneshot`, `regime_chunked`, `regime_agentic`) build on top of this;
`evaluate_models` re-exports the pieces tests and the API regimes reference.
"""

import contextlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

_SCRIPT_DIR = Path(__file__).parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from models.loss_run import FinancialBreakdown, LossRunIncident

# Shared retry shim: use tenacity when available, otherwise no-op decorators.
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


# ============================================================================
# Usage / cost / trace capture (uniform across all regimes)
# ============================================================================
# Token pricing in USD per 1M tokens (defaults = GPT-5.5 standard). Override via env.
PRICE_INPUT_PER_1M = float(os.getenv("LLB_PRICE_INPUT_PER_1M", "5.0"))
PRICE_CACHED_INPUT_PER_1M = float(os.getenv("LLB_PRICE_CACHED_INPUT_PER_1M", "0.5"))
PRICE_OUTPUT_PER_1M = float(os.getenv("LLB_PRICE_OUTPUT_PER_1M", "30.0"))


@dataclass
class CallUsage:
    """Accumulates token usage across the (possibly chunked) calls of one extraction."""
    requests: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0

    def add(self, *, input_tokens=0, cached_input_tokens=0, output_tokens=0, requests=1):
        self.requests += requests
        self.input_tokens += int(input_tokens or 0)
        self.cached_input_tokens += int(cached_input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)

    def cost_usd(self) -> float:
        uncached = max(self.input_tokens - self.cached_input_tokens, 0)
        return round(
            uncached / 1e6 * PRICE_INPUT_PER_1M
            + self.cached_input_tokens / 1e6 * PRICE_CACHED_INPUT_PER_1M
            + self.output_tokens / 1e6 * PRICE_OUTPUT_PER_1M,
            6,
        )

    def as_dict(self) -> dict:
        return {
            "requests": self.requests,
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
        }


# Module-global sink: visible to the extraction worker thread AND its chunk
# sub-threads. Correct for sequential-model runs (one extraction in flight).
_usage_lock = threading.Lock()
_usage_sink: "CallUsage | None" = None


@contextlib.contextmanager
def usage_capture():
    """Capture token usage recorded during the wrapped extraction.

    Yields a CallUsage that the run loop reads afterward. Assumes a single
    extraction is in flight (sequential models); not used for --parallel-models.
    """
    global _usage_sink
    accum = CallUsage()
    with _usage_lock:
        prev = _usage_sink
        _usage_sink = accum
    try:
        yield accum
    finally:
        with _usage_lock:
            _usage_sink = prev


def estimate_cost_usd(*, input_tokens=0, cached_input_tokens=0, output_tokens=0) -> float:
    """USD cost for the given token counts, using the shared PRICE_* rates."""
    u = CallUsage()
    u.add(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
    )
    return u.cost_usd()


def record_usage(*, input_tokens=0, cached_input_tokens=0, output_tokens=0, requests=1):
    """Add token usage to the active capture sink (no-op if none active)."""
    with _usage_lock:
        if _usage_sink is not None:
            _usage_sink.add(
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
                requests=requests,
            )


def record_openai_usage(response) -> None:
    u = getattr(response, "usage", None)
    if u is None:
        return
    ptd = getattr(u, "prompt_tokens_details", None)
    record_usage(
        input_tokens=getattr(u, "prompt_tokens", 0) or 0,
        cached_input_tokens=(getattr(ptd, "cached_tokens", 0) or 0) if ptd is not None else 0,
        output_tokens=getattr(u, "completion_tokens", 0) or 0,
    )


def record_gemini_usage(response) -> None:
    u = getattr(response, "usage_metadata", None)
    if u is None:
        return
    record_usage(
        input_tokens=getattr(u, "prompt_token_count", 0) or 0,
        cached_input_tokens=getattr(u, "cached_content_token_count", 0) or 0,
        output_tokens=getattr(u, "candidates_token_count", 0) or 0,
    )


def record_anthropic_usage(response) -> None:
    u = getattr(response, "usage", None)
    if u is None:
        return
    record_usage(
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        cached_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            output_tokens=getattr(u, "output_tokens", 0) or 0,
    )


def gemini_thinking_config(model_id: str):
    """Return the Gemini thinking config for extraction calls.

    Gemini Pro preview models can consume the output budget as hidden thinking
    tokens. For long-list extraction that often means no JSON is emitted before
    MAX_TOKENS. Default to budget 0 so output capacity is reserved for records;
    override with LLB_GEMINI_THINKING_BUDGET when intentionally testing thinking.
    """
    from google.genai import types

    budget_text = os.getenv("LLB_GEMINI_THINKING_BUDGET", "0").strip()
    if not budget_text:
        return None
    return types.ThinkingConfig(thinking_budget=int(budget_text))


def traces_enabled() -> bool:
    """Debug flag: write per-call/per-run traces when LLB_CAPTURE_TRACES=1."""
    return os.getenv("LLB_CAPTURE_TRACES", "0") == "1"


def trace_dir() -> Path:
    return Path(os.getenv("LLB_TRACE_DIR", str(Path(__file__).resolve().parents[1] / ".traces")))


_trace_lock = threading.Lock()


def record_trace(filename: str, entry: dict) -> None:
    """Append one JSON record to <trace_dir>/<filename> (only when traces enabled)."""
    if not traces_enabled():
        return
    try:
        d = trace_dir()
        d.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, default=str)
        with _trace_lock:
            with (d / filename).open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass


# ============================================================================
# Provider client setup
# ============================================================================

def setup_gemini():
    """Configure Gemini API."""
    api_key = os.getenv('VERTEX_AI_API_KEY') or os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("Set VERTEX_AI_API_KEY, GOOGLE_API_KEY, or GEMINI_API_KEY in environment")
    import google.genai as genai
    return genai.Client(api_key=api_key)


def setup_openai():
    """Configure OpenAI API with an inactivity (read) timeout.

    Root cause of the earlier multi-minute hangs: the SDK's default ~600s
    per-request timeout x its retries (~1800s) on a *stalled* connection.
    A single fixed timeout cannot both allow a legitimate long generation
    (a 500-incident one-shot can stream for ~25 min) and abort a stall fast.

    Fix: stream responses and use an httpx timeout with NO overall deadline
    (`timeout=None`) but a bounded **read** timeout. During a healthy
    generation tokens arrive continuously and reset the read timer, so the
    model decides when to stop; a stalled connection sends nothing and trips
    the read timeout quickly, then retries.
    """
    import httpx
    from openai import OpenAI
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in environment")
    read_timeout = float(os.getenv("LLB_OPENAI_READ_TIMEOUT_SECONDS", "180"))
    max_retries = int(os.getenv("LLB_OPENAI_MAX_RETRIES", "2"))
    timeout = httpx.Timeout(None, connect=30.0, read=read_timeout, write=60.0, pool=30.0)
    return OpenAI(api_key=api_key, timeout=timeout, max_retries=max_retries)


def setup_anthropic():
    """Configure Anthropic API."""
    import anthropic
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in environment")
    return anthropic.Anthropic(api_key=api_key)


# ============================================================================
# Schema + shared prompt
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

_GENERIC_PROMPT_EXCLUDED_FIELDS = {"record_id", "applies_to_record_id"}


def ifta_return_schedule_scope_rules(all_fields: set[str]) -> list[str]:
    """Return IFTA scope rules when the target fields identify a return schedule."""
    if not {"schedule", "jurisdiction"}.issubset(all_fields):
        return []
    return [
        "",
        "IFTA return-schedule rules:",
        "- Include every jurisdiction row, every Non-IFTA row, and every row labeled Return Totals.",
        "- Exclude intermediate subtotals, payment lines, and remittance lines.",
    ]


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


def build_record_extraction_contract(ground_truth: list[dict]) -> str:
    """Build a field contract for generic 2.0 records without leaking target values."""
    by_type: dict[str, set[str]] = {}
    all_fields: set[str] = set()
    has_record_type = any(
        isinstance(record, dict) and "record_type" in record for record in ground_truth
    )

    for record in ground_truth:
        if not isinstance(record, dict):
            continue
        record_type = str(record.get("record_type") or "record") if has_record_type else "record"
        fields = {str(k) for k in record.keys()} - _GENERIC_PROMPT_EXCLUDED_FIELDS
        by_type.setdefault(record_type, set()).update(fields)
        all_fields.update(fields)

    lines = [
        "Output JSON shape:",
        '{ "records": [ ... ] }',
        "",
        "General requirements:",
        "- Extract every target record visible in the document.",
        "- Use the exact field names below; do not invent fields that are not listed.",
    ]
    if has_record_type:
        lines.append("- Every output object must include record_type.")
    else:
        lines.append("- Do not add record_type unless it is visible in the document.")
    lines.extend(
        [
            "- If a listed field is not visible for a record, use an empty string.",
            "- Preserve identifiers, dates, codes, locations, limits, rates, totals, names, and premiums exactly as shown.",
            "- Do not deduplicate repeated records unless they are exact duplicate rows for the same item.",
            "",
            "Allowed record groups and fields:",
        ]
    )

    for record_type in sorted(by_type):
        fields = ", ".join(sorted(by_type[record_type]))
        lines.append(f"- {record_type}: {fields}")

    lines.extend(
        [
            "",
            "All allowed fields:",
            ", ".join(sorted(all_fields)),
            "",
            "Target-scope rules:",
            "- Extract records that match the listed fields, not every nearby note, notice, subtotal, or support table.",
            "- Keep each field to its own value; do not include neighboring labels or carried-over header text.",
            "- For tables split across pages or sections, preserve the inherited row context needed to complete each record.",
            "- For policy packets, extract scheduled locations, classifications, coverages, forms, endorsements, material clauses, rating rows, and premium rows that match the allowed fields.",
            "- For operations documents, extract one record per target table row or section-row combination matching the allowed fields.",
        ]
    )
    lines.extend(ifta_return_schedule_scope_rules(all_fields))
    if "policy_clause_item" in by_type:
        lines.extend(
            [
                "",
                "Policy logical-record rules:",
                "- Return one record per distinct logical policy item, not one record per place where that item appears.",
                "- Evidence for one item may be split across declarations, schedules, forms, endorsements, and clause pages. Join those fields into one complete record using the shared coverage, location, building, class, state, territory, or form context.",
                "- Do not emit separate partial records for restatements of the same item. Deduplicate exact logical records after joining their evidence.",
                "- policy_location_item is a distinct scheduled location/class combination; deduplicate identical restatements.",
                "- policy_form_item is a form linked to a scheduled target item. Exclude unlinked notices, generic policy-jacket information, and repeated form restatements.",
                "- policy_premium_item is an item-level scheduled premium or rating record. Exclude document-level totals and merge repeated presentations of the same item.",
                "- For policy_clause_item, omit section numbers from clause_title, use the normalized category word (such as condition, limitation, or exclusion) for clause_type, and put only the operative provision paragraph in clause_text. Exclude the preceding context or introduction sentence.",
            ]
        )
    return "\n".join(lines)


def build_record_extraction_prompt(ocr_text: str, ground_truth: list[dict]) -> str:
    """Build the one-shot prompt for generic record-list extraction."""
    return f"""Extract all target records from the following document.

{build_record_extraction_contract(ground_truth)}

Output MUST be valid JSON.

Document:
{ocr_text}
"""


# ============================================================================
# JSON parsing / repair
# ============================================================================

def _repair_truncated_array_json(raw: str, key: str | None) -> dict | list | None:
    """Salvage complete objects from a truncated JSON array.

    When the LLM hits the output-token limit the JSON may be cut mid-object.
    This helper finds the last complete object in the target array and returns
    a valid partial result for scoring.
    """
    if key is None:
        arr_start = raw.find("[")
    else:
        idx = raw.find(f'"{key}"')
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

    array_text = search_region[: last_good + 1] + "]"
    repaired = array_text if key is None else '{"' + key + '": ' + array_text + "}"
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


def _repair_truncated_json(raw: str) -> dict | list | None:
    """Salvage complete records/incidents from truncated JSON output."""
    for key in ("incidents", "records"):
        repaired = _repair_truncated_array_json(raw, key)
        if repaired is not None:
            return repaired
    return _repair_truncated_array_json(raw, None)


def parse_json_response(response_text: str) -> Any:
    """Parse JSON from LLM response, handling markdown code blocks."""
    if response_text is None:
        raise ValueError("Model response did not include text")
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


# ============================================================================
# Schema validation
# ============================================================================

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


# ============================================================================
# Chunking helpers (shared by the chunked regime + Gemini engine)
# ============================================================================

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


# ============================================================================
# Provider call engines (used by the regime modules)
# ============================================================================

def _extract_with_gemini_mode(
    client,
    ocr_text: str,
    model_id: str,
    *,
    allow_chunking: bool,
    structured_output: bool,
) -> list[dict]:
    """Gemini engine shared by the one-shot and chunked regimes."""
    from google.genai import types

    def _extract_chunk(chunk_text: str) -> list[dict]:
        prompt = EXTRACTION_PROMPT.format(
            ocr_text=chunk_text,
            schema_json=_LOSS_RUN_EXTRACTION_SCHEMA_JSON,
        )
        thinking_config = gemini_thinking_config(model_id)

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
        record_gemini_usage(response)
        record_trace("gemini_calls.jsonl", {"model": model_id, "input_chars": len(chunk_text)})
        if not response.text:
            finish_reason = None
            if getattr(response, "candidates", None):
                finish_reason = getattr(response.candidates[0], "finish_reason", None)
            raise ValueError(f"Gemini returned no text (finish_reason={finish_reason})")
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


def _openai_supports_custom_temperature(model_id: str) -> bool:
    """Reasoning-family models (gpt-5.x, o-series) only allow the default temperature."""
    m = model_id.lower()
    return not (
        m.startswith("gpt-5")
        or m.startswith("o1")
        or m.startswith("o3")
        or m.startswith("o4")
    )


def _openai_extract_once(
    client,
    text: str,
    model_id: str,
    *,
    max_output_tokens: int = 16384,
) -> list[dict]:
    """One OpenAI call on a single text blob → validated incidents.

    Used per-chunk by the chunked regime and once (with a large output budget)
    by the one-shot regime. Structured-parse first, JSON-mode fallback.
    """
    prompt = EXTRACTION_PROMPT.format(
        ocr_text=text,
        schema_json=_LOSS_RUN_EXTRACTION_SCHEMA_JSON,
    )
    # Responses are streamed so the client's read (inactivity) timeout can abort
    # a stalled connection without capping a long, healthy generation.
    common_kwargs: dict = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": max_output_tokens,
        "stream_options": {"include_usage": True},
    }
    is_reasoning = not _openai_supports_custom_temperature(model_id)
    if not is_reasoning:
        # gpt-5.x / o-series reject temperature=0; only set it for other models.
        common_kwargs["temperature"] = 0
    else:
        # Reasoning models accept reasoning_effort; default to "low" (extraction is
        # mechanical) for speed/cost, overridable. "none"/"" disables the param.
        effort = os.getenv("LLB_OPENAI_REASONING_EFFORT", "low").strip()
        if effort and effort.lower() != "none":
            common_kwargs["reasoning_effort"] = effort
    try:
        with client.beta.chat.completions.stream(
            response_format=LossRunExtraction, **common_kwargs
        ) as stream:
            for _ in stream:
                pass
            final = stream.get_final_completion()
        record_openai_usage(final)
        msg = final.choices[0].message
        parsed = getattr(msg, "parsed", None)
        raw = parsed if parsed is not None else parse_json_response(msg.content)
    except Exception:
        # Fallback: streamed JSON mode for models without the structured-parse endpoint.
        parts: list[str] = []
        usage = None
        response = client.chat.completions.create(
            response_format={"type": "json_object"}, stream=True, **common_kwargs
        )
        for chunk in response:
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
        if usage is not None:
            ptd = getattr(usage, "prompt_tokens_details", None)
            record_usage(
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                cached_input_tokens=(getattr(ptd, "cached_tokens", 0) or 0) if ptd is not None else 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            )
        raw = parse_json_response("".join(parts))
    record_trace("openai_calls.jsonl", {
        "model": model_id,
        "input_chars": len(text),
        "max_output_tokens": max_output_tokens,
    })
    return _validate_and_normalize_predictions(raw)
