#!/usr/bin/env python3
"""Agentic extraction regime: OpenAI Agents SDK + local Docker sandbox.

Unlike the one-shot and auto-chunked regimes, the model is given ONLY the OCR of
the document inside a sandbox and figures out the extraction itself with the
agent's built-in tools. We state the goal, I/O contract, and schema, and let the
model decide how to work. It writes output/incidents.json, read back via the
session. Per-run token usage, cost, and behavior are captured to a local trace.

`agents.*` and `docker` are imported lazily inside functions so this module (and
the rest of the benchmark) imports cleanly without the heavy SDK installed.
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    from .extraction_core import (
        _LOSS_RUN_EXTRACTION_SCHEMA_JSON,
        _validate_and_normalize_predictions,
        estimate_cost_usd,
        ifta_return_schedule_scope_rules,
        parse_json_response,
        record_usage,
        trace_dir,
        traces_enabled,
    )
    from .evaluation_metrics import normalize_record_predictions, uses_record_evaluator
except ImportError:
    from extraction_core import (
        _LOSS_RUN_EXTRACTION_SCHEMA_JSON,
        _validate_and_normalize_predictions,
        estimate_cost_usd,
        ifta_return_schedule_scope_rules,
        parse_json_response,
        record_usage,
        trace_dir,
        traces_enabled,
    )
    from evaluation_metrics import normalize_record_predictions, uses_record_evaluator


_AGENT_INPUT_FILE = "docs/document_ocr.md"
_INCIDENT_OUTPUT_FILE = "output/incidents.json"
_RECORD_OUTPUT_FILE = "output/records.json"
_POLICY_AGENT_EXCLUDED_FIELDS = {"record_id", "applies_to_record_id"}

AGENT_INCIDENT_INSTRUCTIONS = """You extract structured data from a document.

In your sandbox workspace:
- Input:  {input_file} — the OCR of one insurance loss-run document.
- Output: {output_file} — write your result here.

You have a full Linux sandbox: you can run shell commands and Python, read,
search, and slice files, install packages, and write files. The document may be
large. How you approach the extraction is up to you — choose whatever you judge
most reliable for this document.

Goal: extract EVERY incident record from the document into output/incidents.json
as a JSON object of the form {{"incidents": [ ... ]}}.

Field requirements (per the schema below):
- Every incident must include ALL fields in the schema.
- Unknown values: required string fields -> "" ; optional fields -> null ;
  list fields -> [] ; numeric fields -> 0.0.
- Capture the underlying value only: strip OCR/markdown artifacts such as
  surrounding *emphasis* markers or alignment padding.

Verify your output before finishing — do not trust a first pass:
- Confirm you captured every record and none are missing or truncated.
- Spot-check records from different parts of the document (beginning, middle, and
  end), comparing every field against the source — not just the first few records.
- Each field must hold only its own value: no text belonging to a neighboring
  field or label, and no value carried over from another record or from a header.
- Fix any mismatches you find, then re-check.
- Ensure output/incidents.json is valid JSON that conforms to the schema.
- When finished, also print the final JSON object once as a ```json code block.

Schema (JSON Schema):
{schema_json}
""".format(
    input_file=_AGENT_INPUT_FILE,
    output_file=_INCIDENT_OUTPUT_FILE,
    schema_json=_LOSS_RUN_EXTRACTION_SCHEMA_JSON,
)


_INCIDENT_TASK_PROMPT = (
    f"Extract all incidents from {_AGENT_INPUT_FILE} into {_INCIDENT_OUTPUT_FILE}."
)

# Per-document sandbox working dirs must live under the repo root: the SDK's
# manifest materializer rejects local sources outside its base dir (e.g. /tmp,
# which is a symlink to /private/tmp on macOS).
_AGENT_RUN_ROOT = Path(__file__).resolve().parents[1] / ".agent_runs"


def _truncate(text: object, limit: int) -> str:
    s = text if isinstance(text, str) else str(text)
    return s if len(s) <= limit else s[:limit] + f"...(+{len(s) - limit} chars)"


def _usage_to_dict(usage) -> dict | None:
    """Flatten an agents.usage.Usage into a plain dict (tokens + cache/reasoning detail)."""
    if usage is None:
        return None
    itd = getattr(usage, "input_tokens_details", None)
    otd = getattr(usage, "output_tokens_details", None)
    return {
        "requests": getattr(usage, "requests", None),
        "input_tokens": getattr(usage, "input_tokens", None),
        "cached_input_tokens": getattr(itd, "cached_tokens", None) if itd is not None else None,
        "output_tokens": getattr(usage, "output_tokens", None),
        "reasoning_tokens": getattr(otd, "reasoning_tokens", None) if otd is not None else None,
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def _field_summary_for_records(ground_truth: list[dict]) -> str:
    """Describe the record output contract without leaking target values."""
    by_type: dict[str, set[str]] = {}
    all_fields: set[str] = set()
    has_record_type = any(isinstance(record, dict) and "record_type" in record for record in ground_truth)
    for record in ground_truth:
        if not isinstance(record, dict):
            continue
        record_type = str(record.get("record_type") or "record") if has_record_type else "record"
        fields = {str(k) for k in record.keys()} - _POLICY_AGENT_EXCLUDED_FIELDS
        by_type.setdefault(record_type, set()).update(fields)
        all_fields.update(fields)

    lines = [
        "Output JSON shape:",
        '{ "records": [ ... ] }',
        "",
        "General requirements:",
        "- Extract every target record visible in the document.",
        "- Use the exact field names below; do not invent benchmark-only fields that are not listed.",
        "- If a listed field is not visible for a record, use an empty string.",
        "- Preserve identifiers, dates, codes, locations, limits, rates, totals, names, and premiums exactly as shown.",
        "- Do not deduplicate repeated records unless they are exact duplicate rows for the same policy item.",
        "",
        "Allowed record groups and fields:",
    ]
    if has_record_type:
        lines.insert(lines.index("- Use the exact field names below; do not invent benchmark-only fields that are not listed."), "- Every output object must include record_type.")
    else:
        lines.insert(lines.index("- Use the exact field names below; do not invent benchmark-only fields that are not listed."), "- Do not add record_type unless it is visible in the document.")
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
            "- Extract records that match the listed fields, not every nearby note, notice, subtotal, or generic form mention.",
            "- Do not create records whose key scoping fields are blank when those fields are listed for that record type.",
            "- For bop_coverage_item, require a location_number, building_number, scheduled coverage name, limit, class_code, and premium; ignore general liability limits that are not location/building scheduled property rows.",
            "- For policy_premium_item, require the scheduled premium basis plus the item/location/class fields listed for that record type.",
            "- For policy_form_item, extract form rows tied to the scheduled target items; do not extract unrelated policy-jacket, notice, or generic carrier form rows unless the listed fields tie them to a target item.",
            "- For policy_endorsement_item, extract endorsement/detail rows tied to a scheduled target item; do not extract every reference to an endorsement title in prose.",
            "- For policy_location_item, extract one record per unique scheduled location/building/classification row, not one per repeated mention.",
        ]
    )
    lines.extend(ifta_return_schedule_scope_rules(all_fields))
    return "\n".join(lines)


def _build_agent_contract(ground_truth: list[dict] | None) -> tuple[str, str, str, bool]:
    """Return instructions, task prompt, output file, and whether records are expected."""
    if ground_truth and uses_record_evaluator(ground_truth):
        record_contract = _field_summary_for_records(ground_truth)
        instructions = f"""You extract structured data from a document.

In your sandbox workspace:
- Input:  {_AGENT_INPUT_FILE} - the OCR of one commercial insurance or trucking operations document.
- Output: {_RECORD_OUTPUT_FILE} - write your result here.

You have a full Linux sandbox: you can run shell commands and Python, read,
search, and slice files, install packages, and write files. The document may be
large. How you approach the extraction is up to you - choose whatever you judge
most reliable for this document.

Goal: extract EVERY target record from the document into {_RECORD_OUTPUT_FILE}.

The document may contain dense tables, spreadsheet exports, declarations,
locations, rating schedules, forms, endorsements, premium summaries, or distant
supporting sections. Verify records against multiple sections when a field is
defined away from the main list.

{record_contract}

Verify your output before finishing:
- Confirm you captured records across the beginning, middle, and end of the packet.
- Spot-check records from each record group against the source text.
- Ensure each field holds only its own value, with no neighboring labels or carried-over values.
- Ensure {_RECORD_OUTPUT_FILE} is valid JSON.
- When finished, also print the final JSON object once as a ```json code block.
"""
        task_prompt = f"Extract all target records from {_AGENT_INPUT_FILE} into {_RECORD_OUTPUT_FILE}."
        return instructions, task_prompt, _RECORD_OUTPUT_FILE, True

    return AGENT_INCIDENT_INSTRUCTIONS, _INCIDENT_TASK_PROMPT, _INCIDENT_OUTPUT_FILE, False


def _summarize_agent_behavior(new_items) -> list[dict]:
    """Turn a RunResult's new_items into a readable step list (the model's actions)."""
    steps: list[dict] = []
    for item in new_items or []:
        t = type(item).__name__
        raw = getattr(item, "raw_item", None)
        entry: dict = {"item": t}
        if t == "ToolCallItem":
            entry["tool"] = getattr(raw, "name", None) or getattr(raw, "type", None)
            args = getattr(raw, "arguments", None)
            if args is None:
                args = getattr(raw, "action", None) or getattr(raw, "command", None)
            entry["call"] = _truncate(args if args is not None else repr(raw), 800)
        elif t == "ToolCallOutputItem":
            entry["output"] = _truncate(getattr(item, "output", "") or "", 300)
        elif t in ("MessageOutputItem", "ReasoningItem", "CompactionItem"):
            entry["note"] = t
        steps.append(entry)
    return steps


def _write_agent_trace(model_id, ocr_chars, usage, cost, behavior, final_output, retrieval) -> Path | None:
    """Persist a per-run behavior+usage trace locally; never raises into extraction."""
    try:
        out_dir = trace_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        trace = {
            "model_id": model_id,
            "ocr_chars": ocr_chars,
            "retrieval": retrieval,
            "usage": usage,
            "estimated_cost_usd": cost,
            "num_steps": len(behavior),
            "num_tool_calls": sum(1 for b in behavior if b.get("item") == "ToolCallItem"),
            "behavior": behavior,
            "final_output_preview": _truncate(final_output or "", 2000),
        }
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"agent_trace_{stamp}_{os.getpid()}.json"
        path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
        return path
    except Exception:
        return None


def setup_openai_agent():
    """Configure the OpenAI Agents SDK + a local Docker sandbox runtime."""
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not set in environment")
    from docker import from_env as docker_from_env
    docker_client = docker_from_env()
    docker_client.ping()  # fail fast if the Docker daemon is unreachable
    image = os.getenv("LLB_AGENT_SANDBOX_IMAGE", "python:3.14-slim")
    try:
        if not docker_client.images.list(name=image):
            docker_client.images.pull(image)  # pre-pull so it isn't in the per-doc timeout
    except Exception:
        pass  # best-effort; the sandbox will pull on demand otherwise
    return {"docker_client": docker_client, "image": image}


async def _agent_extract_async(client, model_id, work_dir, task_prompt, instructions, output_file):
    """Run the sandbox agent; return dict(final_output, file_bytes, usage, behavior)."""
    from agents import ModelSettings
    from agents import Runner
    from agents.run import RunConfig
    from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
    from agents.sandbox.entries import Dir, LocalFile
    from agents.sandbox.errors import WorkspaceReadNotFoundError
    from agents.sandbox.sandboxes.docker import (
        DockerSandboxClient,
        DockerSandboxClientOptions,
    )
    from openai.types.shared import Reasoning

    manifest = Manifest(entries={
        _AGENT_INPUT_FILE: LocalFile(src=work_dir / _AGENT_INPUT_FILE),
        "output": Dir(description="Write the extracted JSON result here."),
    })
    reasoning_effort = os.getenv("LLB_AGENT_REASONING_EFFORT", "xhigh").strip().lower()
    verbosity = os.getenv("LLB_AGENT_VERBOSITY", "high").strip().lower()
    model_settings = ModelSettings(
        reasoning=Reasoning(effort=reasoning_effort) if reasoning_effort else None,
        verbosity=verbosity if verbosity in {"low", "medium", "high"} else None,
    )
    agent = SandboxAgent(
        name="LongListBench extractor",
        model=model_id,
        model_settings=model_settings,
        instructions=instructions,
        default_manifest=manifest,
    )
    options = DockerSandboxClientOptions(image=client["image"])
    sandbox_client = DockerSandboxClient(client["docker_client"])
    max_turns = int(os.getenv("LLB_AGENT_MAX_TURNS", "60"))

    session = await sandbox_client.create(manifest=manifest, options=options)
    final_output = None
    file_bytes = None
    usage = None
    behavior: list[dict] = []
    async with session:
        result = await Runner.run(
            agent,
            task_prompt,
            run_config=RunConfig(sandbox=SandboxRunConfig(session=session)),
            max_turns=max_turns,
        )
        final_output = getattr(result, "final_output", None)
        usage = _usage_to_dict(getattr(getattr(result, "context_wrapper", None), "usage", None))
        behavior = _summarize_agent_behavior(getattr(result, "new_items", None))
        try:
            stream = await session.read(Path(output_file))
            data = stream.read()
            file_bytes = data if isinstance(data, bytes) else str(data).encode("utf-8")
        except Exception:
            file_bytes = None  # missing/unreadable -> fall back to final_output
    return {
        "final_output": final_output,
        "file_bytes": file_bytes,
        "usage": usage,
        "behavior": behavior,
    }


def _run_agent_extraction(client, model_id, work_dir, task_prompt, instructions, output_file) -> dict:
    """Sync wrapper around the async agent run.

    Safe to call ``asyncio.run`` here: the evaluation harness invokes extract_fn
    inside a fresh ThreadPoolExecutor worker that has no running event loop. This
    function is the seam unit tests monkeypatch to avoid real Docker/API.
    """
    return asyncio.run(_agent_extract_async(client, model_id, work_dir, task_prompt, instructions, output_file))


def extract_with_openai_agent(
    client,
    ocr_text: str,
    model_id: str,
    *,
    ground_truth: list[dict] | None = None,
    sample: str | None = None,
) -> list[dict]:
    """Agentic regime: the model explores the OCR file in a Docker sandbox and extracts itself.

    Not decorated with @retry: agent runs are long and expensive, so a failure
    should surface as an error rather than silently re-running multiple times.
    """
    _AGENT_RUN_ROOT.mkdir(parents=True, exist_ok=True)
    instructions, task_prompt, output_file, expects_records = _build_agent_contract(ground_truth)
    work_dir = Path(tempfile.mkdtemp(prefix="llb_agent_", dir=_AGENT_RUN_ROOT))
    try:
        input_path = work_dir / _AGENT_INPUT_FILE
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_text(ocr_text, encoding="utf-8")

        res = _run_agent_extraction(client, model_id, work_dir, task_prompt, instructions, output_file)
        final_output = res.get("final_output")
        file_bytes = res.get("file_bytes")
        usage = res.get("usage")
        behavior = res.get("behavior") or []
        retrieval = "session_file" if file_bytes else ("final_output" if final_output else "none")

        # Feed usage into the shared sink so the run loop records tokens+cost
        # uniformly (same as the API regimes).
        cost = None
        if usage:
            record_usage(
                input_tokens=usage.get("input_tokens") or 0,
                cached_input_tokens=usage.get("cached_input_tokens") or 0,
                output_tokens=usage.get("output_tokens") or 0,
            )
            cost = estimate_cost_usd(
                input_tokens=usage.get("input_tokens") or 0,
                cached_input_tokens=usage.get("cached_input_tokens") or 0,
                output_tokens=usage.get("output_tokens") or 0,
            )
        trace_path = (
            _write_agent_trace(model_id, len(ocr_text), usage, cost, behavior, final_output, retrieval)
            if traces_enabled()
            else None
        )
        n_calls = sum(1 for b in behavior if b.get("item") == "ToolCallItem")
        u_in = usage.get("input_tokens") if usage else None
        u_out = usage.get("output_tokens") if usage else None
        print(
            f"    [agent] tool_calls={n_calls} tokens(in/out)={u_in}/{u_out} "
            f"est_cost=${cost if cost is not None else '?'} retrieval={retrieval} trace={trace_path}",
            flush=True,
        )

        raw = None
        if file_bytes:
            try:
                raw = json.loads(file_bytes.decode("utf-8"))
            except Exception:
                raw = None
        if raw is None and final_output:
            raw = parse_json_response(final_output)
        if raw is None:
            raise ValueError(
                f"Agent produced neither a readable {output_file} nor parseable final output"
            )

        return normalize_record_predictions(raw) if expects_records else _validate_and_normalize_predictions(raw)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
