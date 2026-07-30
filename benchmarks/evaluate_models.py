#!/usr/bin/env python3
"""Multi-model evaluation script for the LongListBench benchmark."""

import argparse
import contextlib
import hashlib
import inspect
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

_SCRIPT_DIR = Path(__file__).parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    from .evaluation_metrics import (
        evaluate_extraction,
        evaluate_record_extraction,
        normalize_record_predictions,
        uses_record_evaluator,
    )
except ImportError:
    from evaluation_metrics import (
        evaluate_extraction,
        evaluate_record_extraction,
        normalize_record_predictions,
        uses_record_evaluator,
    )

try:
    from .dataset_layout import (
        default_dataset_dir,
        ground_truth_path,
        iter_transcript_paths,
        sample_id_from_transcript_path,
        transcript_path,
    )
except ImportError:
    from dataset_layout import (
        default_dataset_dir,
        ground_truth_path,
        iter_transcript_paths,
        sample_id_from_transcript_path,
        transcript_path,
    )

try:
    from .evaluation_roles import evaluation_role
except ImportError:
    from evaluation_roles import evaluation_role

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
# Model registry
# ============================================================================

@dataclass
class ModelConfig:
    name: str
    provider: str
    model_id: str
    setup_fn: Callable
    extract_fn: Callable


def _setup_offline_only_model():
    raise RuntimeError("This model key is for offline scoring of externally generated predictions")


def _extract_offline_only_model(*args, **kwargs):
    raise RuntimeError("This model key is for offline scoring of externally generated predictions")


# ============================================================================
# Extraction regimes — shared core + one module per regime
# ============================================================================
try:
    from .extraction_core import (
        EXTRACTION_PROMPT,
        LossRunExtraction,
        _BREAKDOWN_FIELDS,
        _BREAKDOWN_KEYS,
        _LOSS_RUN_EXTRACTION_SCHEMA_JSON,
        _LOSS_RUN_FIELDS,
        _repair_truncated_json,
        _validate_and_normalize_predictions,
        _validate_incident_dict_is_complete,
        build_record_extraction_contract,
        parse_json_response,
        setup_anthropic,
        setup_gemini,
        setup_openai,
        usage_capture,
    )
    from .regime_oneshot import extract_with_gemini_oneshot, extract_with_openai_oneshot
    from .regime_chunked import (
        extract_with_anthropic,
        extract_with_gemini,
        extract_with_openai,
    )
    from .regime_agentic import extract_with_openai_agent, setup_openai_agent
except ImportError:
    from extraction_core import (
        EXTRACTION_PROMPT,
        LossRunExtraction,
        _BREAKDOWN_FIELDS,
        _BREAKDOWN_KEYS,
        _LOSS_RUN_EXTRACTION_SCHEMA_JSON,
        _LOSS_RUN_FIELDS,
        _repair_truncated_json,
        _validate_and_normalize_predictions,
        _validate_incident_dict_is_complete,
        build_record_extraction_contract,
        parse_json_response,
        setup_anthropic,
        setup_gemini,
        setup_openai,
        usage_capture,
    )
    from regime_oneshot import extract_with_gemini_oneshot, extract_with_openai_oneshot
    from regime_chunked import (
        extract_with_anthropic,
        extract_with_gemini,
        extract_with_openai,
    )
    from regime_agentic import extract_with_openai_agent, setup_openai_agent



MODELS = {
    'gemini': ModelConfig(
        name='Gemini Pro Preview',
        provider='Google',
        model_id=os.getenv('GEMINI_MODEL_ID', 'gemini-3.1-pro-preview'),
        setup_fn=setup_gemini,
        extract_fn=extract_with_gemini,
    ),
    'gemini_oneshot': ModelConfig(
        name='Gemini Pro Preview (One-shot)',
        provider='Google',
        model_id=os.getenv('GEMINI_ONESHOT_MODEL_ID', os.getenv('GEMINI_MODEL_ID', 'gemini-3.1-pro-preview')),
        setup_fn=setup_gemini,
        extract_fn=extract_with_gemini_oneshot,
    ),
    # Alias for backwards compatibility
    'gemini25': ModelConfig(
        name='Gemini Pro Preview',
        provider='Google',
        model_id=os.getenv('GEMINI_25_MODEL_ID', os.getenv('GEMINI_MODEL_ID', 'gemini-3.1-pro-preview')),
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
    # GPT-5.5 across all three regimes (one model, three extraction strategies).
    'gpt55_oneshot': ModelConfig(
        name='GPT-5.5 (One-shot)',
        provider='OpenAI',
        model_id=os.getenv('GPT55_MODEL_ID', 'gpt-5.5'),
        setup_fn=setup_openai,
        extract_fn=extract_with_openai_oneshot,
    ),
    'gpt55_chunked': ModelConfig(
        name='GPT-5.5 (Auto-chunked)',
        provider='OpenAI',
        model_id=os.getenv('GPT55_MODEL_ID', 'gpt-5.5'),
        setup_fn=setup_openai,
        extract_fn=extract_with_openai,
    ),
    'gpt55_agent': ModelConfig(
        name='GPT-5.5 (Agentic Sandbox)',
        provider='OpenAI',
        model_id=os.getenv('GPT55_AGENT_MODEL_ID', 'gpt-5.5'),
        setup_fn=setup_openai_agent,
        extract_fn=extract_with_openai_agent,
    ),
    'codex_gpt55': ModelConfig(
        name='Codex GPT-5.5 (CLI Agentic, xhigh)',
        provider='OpenAI/Codex',
        model_id='gpt-5.5',
        setup_fn=_setup_offline_only_model,
        extract_fn=_extract_offline_only_model,
    ),
    'reducto_deep_extract': ModelConfig(
        name='Reducto Deep Extract v3',
        provider='Reducto',
        model_id='v3',
        setup_fn=_setup_offline_only_model,
        extract_fn=_extract_offline_only_model,
    ),
    'codex_gpt56_sol': ModelConfig(
        name='Codex GPT-5.6-Sol (CLI Agentic, xhigh)',
        provider='OpenAI/Codex',
        model_id='gpt-5.6-sol',
        setup_fn=_setup_offline_only_model,
        extract_fn=_extract_offline_only_model,
    ),
    'bonsai_27b_page_pipeline': ModelConfig(
        name='Ternary Bonsai 27B (Page Map-Reduce, local)',
        provider='PrismML/PagePipeline',
        model_id='prism-ml/Ternary-Bonsai-27B-mlx-2bit',
        setup_fn=_setup_offline_only_model,
        extract_fn=_extract_offline_only_model,
    ),
    'bonsai_27b_together_page_pipeline': ModelConfig(
        name='Ternary Bonsai 27B (Page Map-Reduce, Together)',
        provider='PrismML/Together/PagePipeline',
        model_id='Prism-ML/Ternary-Bonsai-27B',
        setup_fn=_setup_offline_only_model,
        extract_fn=_extract_offline_only_model,
    ),
    'claude_opus48': ModelConfig(
        name='Claude Opus 4.8 (Claude Code CLI Agentic, xhigh)',
        provider='Anthropic/Claude Code',
        model_id='claude-opus-4-8',
        setup_fn=_setup_offline_only_model,
        extract_fn=_extract_offline_only_model,
    ),
    'claude_fable5': ModelConfig(
        name='Claude Fable 5 (Claude Code CLI Agentic, xhigh)',
        provider='Anthropic/Claude Code',
        model_id='claude-fable-5',
        setup_fn=_setup_offline_only_model,
        extract_fn=_extract_offline_only_model,
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
    extraction_time: float | None
    error: str = None
    transcript: str = "ocr"
    tokens: dict = None
    cost_usd: float = None


_QUICK_SAMPLES = [
    "loss_run_external_002",
    "ifta_mileage_by_vehicle_008",
    "multihop_025_001_crosspage",
    "mixed_cgl_040_001",
]


@dataclass(frozen=True)
class EvaluationInput:
    sample: str
    tier: str
    format: str
    transcript: str


def _transcript_input_path(claims_dir: Path, sample: str, transcript: str) -> Path:
    return transcript_path(claims_dir, sample, transcript)


def _prediction_output_path(output_dir: Path, sample: str, transcript: str, model_key: str) -> Path:
    return output_dir / f"{sample}_{transcript}_{model_key}_predicted.json"


def _legacy_prediction_output_path(output_dir: Path, sample: str, transcript: str, model_key: str) -> Path | None:
    if transcript != "ocr":
        return None
    return output_dir / f"{sample}_{model_key}_predicted.json"


_PREDICTION_PROVENANCE_FILE = "prediction_provenance.json"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _prediction_provenance_key(sample: str, transcript: str, model_key: str) -> str:
    return f"{sample}|{transcript}|{model_key}"


def _load_prediction_provenance(output_dir: Path) -> dict[str, dict]:
    path = output_dir / _PREDICTION_PROVENANCE_FILE
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = payload.get("entries")
    return entries if isinstance(entries, dict) else {}


def _write_prediction_provenance(output_dir: Path, entries: dict[str, dict]) -> None:
    path = output_dir / _PREDICTION_PROVENANCE_FILE
    temporary = path.with_suffix(".tmp")
    payload = {"schema_version": 1, "entries": entries}
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _online_input_provenance(
    *,
    entry: EvaluationInput,
    config: ModelConfig,
    model_key: str,
    transcript_text: str,
    ground_truth: list[dict],
) -> dict[str, str | dict[str, str]]:
    contract = (
        build_record_extraction_contract(ground_truth)
        if uses_record_evaluator(ground_truth)
        else _LOSS_RUN_EXTRACTION_SCHEMA_JSON
    )
    try:
        extractor_source = inspect.getsource(config.extract_fn)
    except (OSError, TypeError):
        extractor_source = repr(config.extract_fn)
    settings = {
        key: value
        for key, value in sorted(os.environ.items())
        if key.startswith("LLB_")
    }
    provenance: dict[str, str | dict[str, str]] = {
        "sample": entry.sample,
        "transcript": entry.transcript,
        "model_key": model_key,
        "model_id": config.model_id,
        "transcript_sha256": _sha256_text(transcript_text),
        "field_contract_sha256": _sha256_text(contract),
        "extractor_source_sha256": _sha256_text(extractor_source),
        "runner_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "llb_settings": settings,
    }
    encoded = json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode("utf-8")
    provenance["input_fingerprint_sha256"] = hashlib.sha256(encoded).hexdigest()
    return provenance


def _bind_online_prediction_provenance(
    expected: dict[str, str | dict[str, str]],
    pred_path: Path,
) -> dict[str, str | dict[str, str]]:
    return {
        **expected,
        "prediction_file": pred_path.name,
        "prediction_sha256": hashlib.sha256(pred_path.read_bytes()).hexdigest(),
    }


def _online_resume_matches(
    saved: dict | None,
    expected: dict[str, str | dict[str, str]],
    pred_path: Path | None,
) -> bool:
    if not isinstance(saved, dict) or pred_path is None or not pred_path.is_file():
        return False
    if any(saved.get(key) != value for key, value in expected.items()):
        return False
    return (
        saved.get("prediction_file") == pred_path.name
        and saved.get("prediction_sha256") == hashlib.sha256(pred_path.read_bytes()).hexdigest()
    )


def _metadata_key(sample: str | None, transcript: str | None, model: str | None) -> tuple[str, str, str] | None:
    if not sample or not model:
        return None
    return (sample, transcript or "ocr", model)


def _remember_saved_result_metadata(
    lookup: dict[tuple[str, str, str], dict],
    entry: dict,
) -> None:
    if entry.get("error"):
        return
    key = _metadata_key(entry.get("sample"), entry.get("transcript", "ocr"), entry.get("model"))
    if key is None:
        return

    metadata = lookup.setdefault(key, {})
    extraction_time = entry.get("extraction_time")
    if "extraction_time" not in metadata and extraction_time is not None:
        try:
            t = float(extraction_time)
            if t > 0:
                metadata["extraction_time"] = t
        except (TypeError, ValueError):
            pass

    if "tokens" not in metadata and entry.get("tokens") is not None:
        metadata["tokens"] = entry.get("tokens")
    if "cost_usd" not in metadata and entry.get("cost_usd") is not None:
        metadata["cost_usd"] = entry.get("cost_usd")


def _load_saved_result_metadata(
    *,
    output_dir: Path,
    previous_report_path: Path | None = None,
) -> dict[tuple[str, str, str], dict]:
    """Recover timing/token/cost metadata when saved predictions are reused."""
    lookup: dict[tuple[str, str, str], dict] = {}
    current_report_path = output_dir / "evaluation_report.json"

    run_metadata_path = output_dir / "run_metadata.json"
    if run_metadata_path.exists():
        try:
            run_metadata = json.loads(
                run_metadata_path.read_text(encoding="utf-8")
            )
            model_key = run_metadata.get("model_key")
            default_transcript = run_metadata.get("transcript", "ocr")
            samples = run_metadata.get("samples", {})
            if isinstance(model_key, str) and isinstance(samples, dict):
                for sample_key, sample_metadata in samples.items():
                    if not isinstance(sample_metadata, dict):
                        continue
                    prompt_tokens = sample_metadata.get("prompt_tokens")
                    completion_tokens = sample_metadata.get("completion_tokens")
                    tokens = None
                    if isinstance(prompt_tokens, int) and isinstance(
                        completion_tokens, int
                    ):
                        tokens = {
                            "input_tokens": prompt_tokens,
                            "output_tokens": completion_tokens,
                            "total_tokens": prompt_tokens + completion_tokens,
                        }
                    _remember_saved_result_metadata(
                        lookup,
                        {
                            "model": model_key,
                            "sample": sample_metadata.get("sample", sample_key),
                            "transcript": sample_metadata.get(
                                "transcript", default_transcript
                            ),
                            "extraction_time": sample_metadata.get(
                                "extraction_time"
                            ),
                            "tokens": tokens,
                        },
                    )
        except Exception:
            pass

    report_paths: list[Path] = [current_report_path]
    if previous_report_path is not None:
        try:
            if previous_report_path.resolve() != current_report_path.resolve():
                report_paths.append(previous_report_path)
        except Exception:
            report_paths.append(previous_report_path)
    per_sample_dir = output_dir / "per_sample_reports"
    if per_sample_dir.exists():
        report_paths.extend(sorted(per_sample_dir.glob("*.json")))

    for report_path in report_paths:
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                for entry in report.get("detailed_results", []):
                    _remember_saved_result_metadata(lookup, entry)
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
            stderr=subprocess.DEVNULL,
        )
        head_report = json.loads(head_json)
        for entry in head_report.get("detailed_results", []):
            _remember_saved_result_metadata(lookup, entry)
    except Exception:
        pass

    return lookup


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
            for transcript_path in iter_transcript_paths(claims_dir, transcript):
                if transcript_path.stat().st_size <= 0:
                    continue
                sample = sample_id_from_transcript_path(claims_dir, transcript_path, transcript)
                json_file = ground_truth_path(claims_dir, sample)
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
            json_file = ground_truth_path(claims_dir, sample)
            if transcript_path.exists() and transcript_path.stat().st_size > 0 and json_file.exists():
                out.append(EvaluationInput(sample=sample, tier=tier, format=fmt, transcript=transcript))

    return out


def get_sample_info(sample_name: str) -> tuple[str, str]:
    """Extract tier and format from sample name."""
    if sample_name.startswith(
        (
            "driver_mvr_packet_",
            "driver_schedule_sparse_",
            "ifta_",
            "loss_run_external_",
            "vehicle_schedule_sparse_",
        )
    ):
        return "core_operations", "production_like_pdf"
    if sample_name.startswith(("multihop_bop_", "multihop_wc_", "mixed_cgl_")):
        return "policy_packets", "crosspage"
    if sample_name.startswith(("multihop_", "mixed_")):
        return "claim_multihop", "crosspage"

    parts = sample_name.split('_')
    tier = parts[0]
    fmt = parts[-1]
    return tier, fmt


def _validate_predictions_for_ground_truth(raw: object, ground_truth: list[dict]) -> list[dict]:
    if uses_record_evaluator(ground_truth):
        return normalize_record_predictions(raw)
    return _validate_and_normalize_predictions(raw)


def _evaluate_predictions_for_ground_truth(predicted: list[dict], ground_truth: list[dict]) -> dict:
    if uses_record_evaluator(ground_truth):
        return evaluate_record_extraction(predicted, ground_truth)
    return evaluate_extraction(predicted, ground_truth)


def _record_label_for_ground_truth(ground_truth: list[dict]) -> str:
    return "records" if uses_record_evaluator(ground_truth) else "claims"


def _call_extract_fn(
    extract_fn: Callable,
    client: object,
    transcript_text: str,
    model_id: str,
    *,
    ground_truth: list[dict],
    sample: str,
) -> object:
    """Call an extraction function, passing benchmark context when supported."""
    try:
        params = inspect.signature(extract_fn).parameters
    except (TypeError, ValueError):
        params = {}

    kwargs = {}
    if "ground_truth" in params:
        kwargs["ground_truth"] = ground_truth
    if "sample" in params:
        kwargs["sample"] = sample
    return extract_fn(client, transcript_text, model_id, **kwargs)


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
        claims_dir = default_dataset_dir()
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
        print(
            f"Resume enabled: {existing_pairs}/{total_pairs} prediction files exist; "
            "only provenance-matched files will be reused"
        )
        print()

    if not parallel_models:
        parallel_models = os.getenv("LLB_PARALLEL_MODELS", "0") == "1"

    if model_workers is None:
        model_workers = int(os.getenv("LLB_MODEL_WORKERS", str(len(models))))
    model_workers = max(1, int(model_workers))
    saved_metadata = _load_saved_result_metadata(output_dir=output_dir)
    prediction_provenance = _load_prediction_provenance(output_dir)
    provenance_lock = threading.Lock()

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
        json_path = ground_truth_path(claims_dir, entry.sample)

        transcript_text = transcript_path.read_text(encoding='utf-8')
        with open(json_path) as f:
            ground_truth = json.load(f)
        
        record_label = _record_label_for_ground_truth(ground_truth)
        print(f"  Ground truth: {len(ground_truth)} {record_label}")
        print(f"  {entry.transcript} text: {len(transcript_text):,} characters")
        print()

        input_provenance = {
            model_key: _online_input_provenance(
                entry=entry,
                config=MODELS[model_key],
                model_key=model_key,
                transcript_text=transcript_text,
                ground_truth=ground_truth,
            )
            for model_key in active_models
        }

        def _record_prediction_provenance(model_key: str, pred_path: Path) -> None:
            key = _prediction_provenance_key(entry.sample, entry.transcript, model_key)
            bound = _bind_online_prediction_provenance(input_provenance[model_key], pred_path)
            with provenance_lock:
                prediction_provenance[key] = bound
                _write_prediction_provenance(output_dir, prediction_provenance)

        def _eval_one_model(model_key: str) -> EvaluationResult:
            config = MODELS[model_key]
            client = clients[model_key]

            if model_key.startswith("gemini"):
                _gemini_rate_limit()

            start_time = time.time()
            error = None
            predicted: list[dict] = []
            usage_accum = None
            try:
                extract_timeout_s = float(os.getenv("LLB_EXTRACT_TIMEOUT_SECONDS", "1800"))
                heartbeat_s = float(os.getenv("LLB_EXTRACT_HEARTBEAT_SECONDS", "30"))

                def _do_extract() -> object:
                    return _call_extract_fn(
                        config.extract_fn,
                        client,
                        transcript_text,
                        config.model_id,
                        ground_truth=ground_truth,
                        sample=entry.sample,
                    )

                # Token/cost capture uses a module-global sink, so it's only correct
                # when one extraction is in flight (sequential models). Skip it under
                # --parallel-models to avoid cross-model attribution.
                _capture = contextlib.nullcontext() if parallel_models else usage_capture()
                with ThreadPoolExecutor(max_workers=1) as _ex, _capture as usage_accum:
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
                predicted = _validate_predictions_for_ground_truth(raw_predicted, ground_truth)
            except FuturesTimeoutError:
                error = f"TimeoutError: extraction exceeded {os.getenv('LLB_EXTRACT_TIMEOUT_SECONDS', '1800')}s"
            except Exception as e:
                if RetryError is not None and isinstance(e, RetryError) and getattr(e, "last_attempt", None) is not None:
                    underlying = e.last_attempt.exception()
                    error = f"{type(underlying).__name__}: {underlying}"
                else:
                    error = str(e)

            extraction_time = time.time() - start_time
            tokens = usage_accum.as_dict() if usage_accum and usage_accum.requests else None
            cost_usd = usage_accum.cost_usd() if usage_accum and usage_accum.requests else None

            if not error:
                metrics = _evaluate_predictions_for_ground_truth(predicted, ground_truth)
                pred_path = _prediction_output_path(output_dir, entry.sample, entry.transcript, model_key)
                with open(pred_path, "w") as f:
                    json.dump(predicted, f, indent=2)
                _record_prediction_provenance(model_key, pred_path)
            else:
                metrics = _evaluate_predictions_for_ground_truth([], ground_truth)

            return EvaluationResult(
                model=model_key,
                sample=entry.sample,
                tier=entry.tier,
                format=entry.format,
                metrics=metrics,
                extraction_time=extraction_time,
                error=error,
                transcript=entry.transcript,
                tokens=tokens,
                cost_usd=cost_usd,
            )

        if not parallel_models or len(active_models) <= 1:
            for model_key in active_models:
                pair_index += 1
                config = MODELS[model_key]
                pred_path = _prediction_output_path(output_dir, entry.sample, entry.transcript, model_key)
                legacy_path = _legacy_prediction_output_path(output_dir, entry.sample, entry.transcript, model_key)
                existing_pred_path = pred_path if pred_path.exists() and pred_path.stat().st_size > 0 else legacy_path
                provenance_key = _prediction_provenance_key(entry.sample, entry.transcript, model_key)
                can_resume = resume and _online_resume_matches(
                    prediction_provenance.get(provenance_key),
                    input_provenance[model_key],
                    existing_pred_path,
                )
                if can_resume:
                    try:
                        raw_predicted = json.loads(existing_pred_path.read_text(encoding="utf-8"))
                        predicted = _validate_predictions_for_ground_truth(raw_predicted, ground_truth)
                        metrics = _evaluate_predictions_for_ground_truth(predicted, ground_truth)
                        metadata = saved_metadata.get((entry.sample, entry.transcript, model_key), {})
                        r = EvaluationResult(
                            model=model_key,
                            sample=entry.sample,
                            tier=entry.tier,
                            format=entry.format,
                            metrics=metrics,
                            extraction_time=metadata.get("extraction_time", 0.0),
                            error=None,
                            transcript=entry.transcript,
                            tokens=metadata.get("tokens"),
                            cost_usd=metadata.get("cost_usd"),
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
                    print(f"    Predicted: {m['predicted_count']} {record_label}")
                    print(f"    Recall: {m['recall']:.1%}  Precision: {m['precision']:.1%}  F1: {m['f1']:.1%}")
                    print(f"    Time: {r.extraction_time:.1f}s")
                    if r.cost_usd is not None:
                        t = r.tokens or {}
                        print(f"    Cost: ${r.cost_usd:.4f}  Tokens(in/out): {t.get('input_tokens', 0):,}/{t.get('output_tokens', 0):,}")
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
                    provenance_key = _prediction_provenance_key(entry.sample, entry.transcript, model_key)
                    can_resume = resume and _online_resume_matches(
                        prediction_provenance.get(provenance_key),
                        input_provenance[model_key],
                        existing_pred_path,
                    )
                    if can_resume:
                        try:
                            raw_predicted = json.loads(existing_pred_path.read_text(encoding="utf-8"))
                            predicted = _validate_predictions_for_ground_truth(raw_predicted, ground_truth)
                            metrics = _evaluate_predictions_for_ground_truth(predicted, ground_truth)
                            metadata = saved_metadata.get((entry.sample, entry.transcript, model_key), {})
                            skipped.append(
                                EvaluationResult(
                                    model=model_key,
                                    sample=entry.sample,
                                    tier=entry.tier,
                                    format=entry.format,
                                    metrics=metrics,
                                    extraction_time=metadata.get("extraction_time", 0.0),
                                    error=None,
                                    transcript=entry.transcript,
                                    tokens=metadata.get("tokens"),
                                    cost_usd=metadata.get("cost_usd"),
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
                    print(f"    Predicted: {m['predicted_count']} {record_label}")
                    print(f"    Recall: {m['recall']:.1%}  Precision: {m['precision']:.1%}  F1: {m['f1']:.1%}")
                    print(f"    Time: {r.extraction_time:.1f}s")
                    if r.cost_usd is not None:
                        t = r.tokens or {}
                        print(f"    Cost: ${r.cost_usd:.4f}  Tokens(in/out): {t.get('input_tokens', 0):,}/{t.get('output_tokens', 0):,}")
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
                        print(f"    Predicted: {m['predicted_count']} {record_label}")
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
        claims_dir = default_dataset_dir()
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

    saved_metadata = _load_saved_result_metadata(
        output_dir=output_dir,
        previous_report_path=previous_report_path,
    )

    results: list[EvaluationResult] = []

    for entry in eval_inputs:
        json_path = ground_truth_path(claims_dir, entry.sample)
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
                    predicted = _validate_predictions_for_ground_truth(raw_predicted, ground_truth)
                except Exception as e:
                    error = f"Failed to load predicted JSON: {e}"
            else:
                error = f"Missing predicted file: {pred_path.name}"

            if not error:
                metrics = _evaluate_predictions_for_ground_truth(predicted, ground_truth)
            else:
                metrics = _evaluate_predictions_for_ground_truth([], ground_truth)

            metadata = saved_metadata.get((entry.sample, entry.transcript, model_key), {})

            results.append(
                EvaluationResult(
                    model=model_key,
                    sample=entry.sample,
                    tier=entry.tier,
                    format=entry.format,
                    metrics=metrics,
                    extraction_time=metadata.get("extraction_time"),
                    error=error,
                    transcript=entry.transcript,
                    tokens=metadata.get("tokens"),
                    cost_usd=metadata.get("cost_usd"),
                )
            )

    return results


def _new_group_stats() -> dict:
    return {
        'count': 0,
        'rows': 0,
        'pred_rows': 0,
        'exact_record_matches': 0,
        'complete_documents': 0,
        'f1_sum': 0,
        'recall_sum': 0,
        'found_sum': 0,
        'gold_pairs_sum': 0,
        'pred_pairs_sum': 0,
    }


def _add_result_to_group(group: dict, r: EvaluationResult) -> None:
    group['count'] += 1
    group['rows'] += r.metrics.get('ground_truth_count', 0)
    group['pred_rows'] += r.metrics.get('predicted_count', 0)
    group['exact_record_matches'] += r.metrics.get('exact_record_matches', 0)
    group['complete_documents'] += int(bool(r.metrics.get('complete_document', False)))
    group['f1_sum'] += r.metrics['f1']
    group['recall_sum'] += r.metrics['recall']
    group['found_sum'] += r.metrics.get('found', 0)
    group['gold_pairs_sum'] += r.metrics.get('total_gold_field_pairs', 0)
    group['pred_pairs_sum'] += r.metrics.get('total_pred_field_pairs', 0)


def _finalize_group_stats(groups: dict[str, dict]) -> None:
    for group in groups.values():
        c = group['count']
        group['avg_f1'] = group['f1_sum'] / c if c > 0 else 0
        group['avg_recall'] = group['recall_sum'] / c if c > 0 else 0
        gold_pairs = group['gold_pairs_sum']
        pred_pairs = group['pred_pairs_sum']
        found_sum = group['found_sum']
        exact_matches = group['exact_record_matches']
        pred_rows = group['pred_rows']
        group['exact_record_recall'] = exact_matches / group['rows'] if group['rows'] > 0 else 0
        group['exact_record_precision'] = exact_matches / pred_rows if pred_rows > 0 else 0
        group['exact_record_f1'] = (
            2 * group['exact_record_precision'] * group['exact_record_recall']
            / (group['exact_record_precision'] + group['exact_record_recall'])
            if (group['exact_record_precision'] + group['exact_record_recall']) > 0 else 0
        )
        group['complete_document_rate'] = group['complete_documents'] / c if c > 0 else 0
        group['weighted_recall'] = found_sum / gold_pairs if gold_pairs > 0 else 0
        group['weighted_precision'] = found_sum / pred_pairs if pred_pairs > 0 else 0
        group['weighted_f1'] = (
            2 * group['weighted_precision'] * group['weighted_recall'] / (group['weighted_precision'] + group['weighted_recall'])
            if (group['weighted_precision'] + group['weighted_recall']) > 0 else 0
        )


def _load_manifest_metadata_by_sample() -> dict[str, dict]:
    manifest_path = default_dataset_dir() / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for inst in manifest.get("instances", []):
        sample_id = inst.get("id")
        if sample_id:
            out[str(sample_id)] = inst
    return out


def _current_git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def _git_dirty(ignore_paths: Iterable[Path] = ()) -> bool | None:
    repo_root = Path(__file__).resolve().parents[1]
    ignored: set[str] = set()
    for path in ignore_paths:
        try:
            ignored.add(path.resolve().relative_to(repo_root).as_posix())
        except ValueError:
            continue

    try:
        output = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        for line in output.splitlines():
            if not line:
                continue
            path = line[3:] if len(line) > 3 else ""
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            if (
                path.startswith("benchmarks/results/")
                and Path(path).name in {"evaluation_report.json", "evaluation_report.md"}
            ):
                continue
            if path not in ignored:
                return True
        return False
    except Exception:
        return None


def _dataset_provenance(ignore_dirty_paths: Iterable[Path] = ()) -> dict:
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = default_dataset_dir() / "manifest.json"
    try:
        manifest_display_path = manifest_path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        manifest_display_path = manifest_path.name
    provenance = {
        "manifest_path": manifest_display_path,
        "manifest_sha256": None,
        "git_sha": _current_git_sha(),
        "git_dirty": _git_dirty(ignore_dirty_paths),
    }
    try:
        manifest_bytes = manifest_path.read_bytes()
    except Exception:
        return provenance
    provenance["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    return provenance


def generate_report(
    results: list[EvaluationResult],
    output_path: Path,
    evaluation_mode: str = "live",
):
    """Generate summary report in JSON and Markdown formats."""

    metadata_by_sample = _load_manifest_metadata_by_sample()
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
                'total_pred_rows': 0,
                'total_exact_record_matches': 0,
                'complete_documents': 0,
                'errors': 0,
                'total_cost_usd': None,
                'total_input_tokens': None,
                'total_output_tokens': None,
                'total_extraction_time': None,
                'by_tier': {},
                'by_format': {},
                'by_transcript': {},
                'by_complexity_regime': {},
                'by_evaluation_role': {},
                'by_stressor': {},
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
        stats['total_pred_rows'] += r.metrics.get('predicted_count', 0)
        stats['total_exact_record_matches'] += r.metrics.get('exact_record_matches', 0)
        stats['complete_documents'] += int(bool(r.metrics.get('complete_document', False)))
        if r.cost_usd is not None:
            stats['total_cost_usd'] = (stats['total_cost_usd'] or 0.0) + r.cost_usd
        if r.extraction_time is not None:
            stats['total_extraction_time'] = (
                stats['total_extraction_time'] or 0.0
            ) + r.extraction_time
        if r.tokens:
            stats['total_input_tokens'] = (
                stats['total_input_tokens'] or 0
            ) + r.tokens.get('input_tokens', 0)
            stats['total_output_tokens'] = (
                stats['total_output_tokens'] or 0
            ) + r.tokens.get('output_tokens', 0)
        if r.error:
            stats['errors'] += 1
        
        # By tier
        _add_result_to_group(stats['by_tier'].setdefault(r.tier, _new_group_stats()), r)
        
        # By format
        _add_result_to_group(stats['by_format'].setdefault(r.format, _new_group_stats()), r)

        # By transcript condition
        _add_result_to_group(stats['by_transcript'].setdefault(r.transcript, _new_group_stats()), r)

        metadata = metadata_by_sample.get(r.sample, {})
        complexity_regime = metadata.get("complexity_regime") or metadata.get("difficulty") or r.tier
        _add_result_to_group(
            stats['by_complexity_regime'].setdefault(str(complexity_regime), _new_group_stats()),
            r,
        )
        _add_result_to_group(
            stats['by_evaluation_role'].setdefault(
                evaluation_role(str(complexity_regime)), _new_group_stats()
            ),
            r,
        )
        for stressor in sorted(set(metadata.get("problems") or [])):
            _add_result_to_group(
                stats['by_stressor'].setdefault(str(stressor), _new_group_stats()),
                r,
            )
    
    # Compute averages
    for model, stats in model_stats.items():
        n = stats['total_samples']
        stats['avg_f1'] = stats['total_f1'] / n if n > 0 else 0
        stats['avg_recall'] = stats['total_recall'] / n if n > 0 else 0
        stats['avg_precision'] = stats['total_precision'] / n if n > 0 else 0
        total_found = stats['total_found']
        total_gold = stats['total_gold_field_pairs']
        total_pred = stats['total_pred_field_pairs']
        exact_matches = stats['total_exact_record_matches']
        total_pred_rows = stats['total_pred_rows']
        stats['exact_record_recall'] = exact_matches / stats['total_rows'] if stats['total_rows'] > 0 else 0
        stats['exact_record_precision'] = exact_matches / total_pred_rows if total_pred_rows > 0 else 0
        stats['exact_record_f1'] = (
            2 * stats['exact_record_precision'] * stats['exact_record_recall']
            / (stats['exact_record_precision'] + stats['exact_record_recall'])
            if (stats['exact_record_precision'] + stats['exact_record_recall']) > 0 else 0
        )
        stats['complete_document_rate'] = stats['complete_documents'] / n if n > 0 else 0
        stats['weighted_recall'] = total_found / total_gold if total_gold > 0 else 0
        stats['weighted_precision'] = total_found / total_pred if total_pred > 0 else 0
        stats['weighted_f1'] = (
            2 * stats['weighted_precision'] * stats['weighted_recall'] / (stats['weighted_precision'] + stats['weighted_recall'])
            if (stats['weighted_precision'] + stats['weighted_recall']) > 0 else 0
        )
        
        _finalize_group_stats(stats['by_tier'])
        _finalize_group_stats(stats['by_format'])
        _finalize_group_stats(stats['by_transcript'])
        _finalize_group_stats(stats['by_complexity_regime'])
        _finalize_group_stats(stats['by_evaluation_role'])
        _finalize_group_stats(stats['by_stressor'])
    
    json_path = output_path / 'evaluation_report.json'
    md_path = output_path / 'evaluation_report.md'

    # Save JSON report. Ignore the report files themselves when recording
    # provenance so a report refresh can still point to a clean code/data tree.
    dataset_provenance = _dataset_provenance(ignore_dirty_paths=[json_path, md_path])
    report = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'evaluation_mode': evaluation_mode,
        'dataset': dataset_provenance,
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
                'tokens': r.tokens,
                'cost_usd': r.cost_usd,
                'error': r.error,
            }
            for r in results
        ],
    }
    
    with open(json_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    # Generate Markdown report
    md_lines = [
        "# Multi-Model Evaluation Report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"Evaluation mode: `{evaluation_mode}`",
        f"Dataset manifest SHA-256: `{dataset_provenance.get('manifest_sha256') or 'unknown'}`",
        f"Git SHA: `{dataset_provenance.get('git_sha') or 'unknown'}`; dirty: `{dataset_provenance.get('git_dirty')}`",
        "",
        "## Overall Results",
        "",
        "| Model | Exact-record recall | Complete documents | Field micro-F1 | Field macro-F1 | Rows | Samples | Errors | Time (s) | Cost (USD) |",
        "|-------|---------------------|--------------------|----------------|----------------|------|---------|--------|----------|------------|",
    ]

    def _format_group_pct(group_stats: dict | None, metric: str) -> str:
        if not group_stats or group_stats.get("count", 0) == 0:
            return "N/A"
        return f"{group_stats[metric]:.1%}"

    def _observed_group_keys(stats_key: str, preferred_order: list[str]) -> list[str]:
        observed: set[str] = set()
        for model_key in model_order:
            if model_key in model_stats:
                observed.update(model_stats[model_key].get(stats_key, {}).keys())
        return [
            *[key for key in preferred_order if key in observed],
            *sorted(observed - set(preferred_order)),
        ]

    def _label_group_key(key: str) -> str:
        return key.replace("_", " ").title()

    def _format_summary_time(seconds: float | None) -> str:
        if evaluation_mode == "offline_replay" or seconds is None:
            return "N/A"
        return f"{seconds:.0f}"

    def _format_summary_cost(cost_usd: float | None) -> str:
        if evaluation_mode == "offline_replay" or cost_usd is None:
            return "N/A"
        return f"${cost_usd:.4f}"

    def _format_detail_time(seconds: float | None) -> str:
        if evaluation_mode == "offline_replay" or seconds is None:
            return "N/A"
        return f"{seconds:.1f}s"

    def _append_group_table(title: str, stats_key: str, preferred_order: list[str]) -> None:
        group_keys = _observed_group_keys(stats_key, preferred_order)
        if not group_keys:
            return

        headers = ["Model", *[_label_group_key(key) for key in group_keys]]
        md_lines.extend(
            [
                "",
                title,
                "",
                "| " + " | ".join(headers) + " |",
                "|" + "|".join(["---"] * len(headers)) + "|",
            ]
        )

        for model_key in model_order:
            if model_key in model_stats:
                s = model_stats[model_key]
                name = MODELS[model_key].name
                scores = [
                    _format_group_pct(s[stats_key].get(key), "exact_record_recall")
                    for key in group_keys
                ]
                md_lines.append(f"| {name} | {' | '.join(scores)} |")

    for model_key in model_order:
        if model_key in model_stats:
            s = model_stats[model_key]
            name = MODELS[model_key].name
            md_lines.append(
                f"| {name} | {s['exact_record_recall']:.1%} | "
                f"{s['complete_documents']}/{s['total_samples']} ({s['complete_document_rate']:.1%}) | "
                f"{s['weighted_f1']:.1%} | {s['avg_f1']:.1%} | {s['total_rows']} | "
                f"{s['total_samples']} | {s['errors']} | "
                f"{_format_summary_time(s.get('total_extraction_time', 0.0))} | {_format_summary_cost(s.get('total_cost_usd', 0.0))} |"
            )
    
    md_lines.extend([
        "",
        "The primary score is exact-record recall: a target counts only when every normalized field in one predicted record matches one ground-truth record. Complete-document success additionally requires the predicted and ground-truth record multisets to be identical. Record order is not scored. Field-pair F1 remains a secondary diagnostic.",
    ])

    _append_group_table(
        "## Strict Completeness by Evaluation Role",
        "by_evaluation_role",
        ["structural_challenge", "scale_control", "unclassified"],
    )

    _append_group_table(
        "## Strict Completeness by Difficulty Tier",
        "by_tier",
        [
            "core_operations",
            "claim_multihop",
            "policy_packets",
            "easy",
            "medium",
            "hard",
            "extreme",
            "multihop",
            "mixed",
        ],
    )
    _append_group_table(
        "## Strict Completeness by Document Format",
        "by_format",
        ["production_like_pdf", "crosspage", "detailed", "table"],
    )

    _append_group_table(
        "## Strict Completeness by Complexity Regime",
        "by_complexity_regime",
        [
            "ifta_mileage_by_vehicle",
            "ifta_multisection_return_packet",
            "ifta_return_schedule_details",
            "ifta_tax_return_summary",
            "driver_mvr_request_and_roster",
            "loss_run_external",
            "vehicle_schedule_spreadsheet_export",
            "ifta_tax_return_inquiry_detail",
            "driver_schedule_spreadsheet_export",
            "claim_crosspage_multihop",
            "policy_multi_hop",
        ],
    )

    _append_group_table(
        "## Strict Completeness by Key Stressor",
        "by_stressor",
        [
            "ocr_layout_condition",
            "cross_section_join",
            "long_range_evidence",
            "heterogeneous_record_list",
            "multi_column",
            "merged_cells",
            "multi_row",
            "duplicates",
            "distractor_sections",
            "repeated_keys",
            "large_doc",
            "high_density_long_list",
            "page_breaks",
        ],
    )

    md_lines.extend([
        "",
        "## Strict Completeness by Transcript Condition",
        "",
        "| Model | Canonical | OCR |",
        "|-------|-----------|-----|",
    ])

    for model_key in model_order:
        if model_key in model_stats:
            s = model_stats[model_key]
            name = MODELS[model_key].name
            canonical = _format_group_pct(s["by_transcript"].get("canonical"), "exact_record_recall")
            ocr = _format_group_pct(s["by_transcript"].get("ocr"), "exact_record_recall")
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
            md_lines.append("| Model | Exact records | Complete | Field F1 | Predicted | Time |")
            md_lines.append("|-------|---------------|----------|----------|-----------|------|")
            
            for r2 in results:
                if r2.sample == r.sample and r2.transcript == r.transcript:
                    name = MODELS[r2.model].name
                    m = r2.metrics
                    if r2.error:
                        md_lines.append(f"| {name} | ERROR | - | - | - | - |")
                    else:
                        gold_count = m.get('ground_truth_count', 0)
                        predicted_count = m.get('predicted_count', 0)
                        exact_matches = m.get('exact_record_matches', 0)
                        exact_recall = m.get(
                            'exact_record_recall',
                            exact_matches / gold_count if gold_count > 0 else float(predicted_count == 0),
                        )
                        complete_document = m.get(
                            'complete_document',
                            exact_matches == gold_count == predicted_count,
                        )
                        md_lines.append(
                            f"| {name} | {exact_recall:.1%} | "
                            f"{'yes' if complete_document else 'no'} | {m['f1']:.1%} | "
                            f"{m['predicted_count']} | {_format_detail_time(r2.extraction_time)} |"
                        )
            
            md_lines.append("")
    
    with open(md_path, 'w') as f:
        f.write('\n'.join(md_lines))
    
    print(f"\nReports saved to:")
    print(f"  - {json_path}")
    print(f"  - {md_path}")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Multi-model evaluation for LongListBench')
    parser.add_argument('--models', nargs='+', default=['gpt55_oneshot'],
                       choices=sorted(MODELS),
                       help='Models to evaluate (default: gpt55_oneshot)')
    parser.add_argument('--output-dir', default=None,
                       help='Directory to write predictions and evaluation reports (default: benchmarks/results/scratch)')
    parser.add_argument('--tiers', nargs='+', default=None,
                       choices=['easy', 'medium', 'hard', 'extreme', 'multihop', 'mixed',
                                'core_operations', 'claim_multihop', 'policy_packets'],
                       help='Difficulty tiers to test (default: all)')
    parser.add_argument('--formats', nargs='+', default=None,
                       choices=['detailed', 'table', 'crosspage', 'production_like_pdf'],
                       help='Document formats to test (default: all)')
    parser.add_argument('--transcripts', nargs='+', default=['ocr'],
                       choices=['canonical', 'ocr'],
                       help='Transcript conditions to test (default: ocr)')
    parser.add_argument('--samples', nargs='+', default=None,
                       help='Specific samples to test (default: all available)')
    parser.add_argument('--quick', action='store_true',
                       help='Quick test with representative current-release samples')
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
    return parser


def main():
    parser = build_argument_parser()
    args = parser.parse_args()
    
    # Quick mode: representative current-release samples.
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
    generate_report(results, output_dir, evaluation_mode="offline_replay" if args.offline else "live")
    
    print()
    print("="*70)
    print("EVALUATION COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
