#!/usr/bin/env python3
"""Run repository-denied Codex CLI extraction and score saved predictions.

Each sample is copied into a temporary workspace containing only:
- document_ocr.md
- field_contract.md
- prompt.md

The Codex process is wrapped in a macOS sandbox profile that denies read/write
access to this repository. The prompt also prohibits using files outside the
temporary workspace. This is repository isolation, not a host-wide filesystem
allowlist. The runner validates the output and saves the normalized prediction.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

try:
    from .dataset_layout import (
        default_dataset_dir,
        ground_truth_path,
        iter_transcript_paths,
        sample_id_from_transcript_path,
        transcript_path,
    )
    from .evaluate_models import MODELS, generate_report, run_evaluation_from_saved_predictions
    from .evaluation_metrics import normalize_record_predictions, uses_record_evaluator
    from .extraction_core import (
        _LOSS_RUN_EXTRACTION_SCHEMA_JSON,
        _validate_and_normalize_predictions,
        build_record_extraction_contract,
        parse_json_response,
    )
except ImportError:
    from dataset_layout import (
        default_dataset_dir,
        ground_truth_path,
        iter_transcript_paths,
        sample_id_from_transcript_path,
        transcript_path,
    )
    from evaluate_models import MODELS, generate_report, run_evaluation_from_saved_predictions
    from evaluation_metrics import normalize_record_predictions, uses_record_evaluator
    from extraction_core import (
        _LOSS_RUN_EXTRACTION_SCHEMA_JSON,
        _validate_and_normalize_predictions,
        build_record_extraction_contract,
        parse_json_response,
    )


DEFAULT_MODEL_KEY = "codex_gpt55"
DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_REASONING_EFFORT = "xhigh"
RUN_METADATA_FILE = "run_metadata.json"
OUTPUT_FILE_RECORDS = Path("output/records.json")
OUTPUT_FILE_INCIDENTS = Path("output/incidents.json")


def discover_samples(dataset_dir: Path, transcript: str, requested: list[str] | None) -> list[str]:
    if requested:
        return requested
    samples: list[tuple[int, str]] = []
    for path in iter_transcript_paths(dataset_dir, transcript):
        if path.stat().st_size <= 0:
            continue
        sample = sample_id_from_transcript_path(dataset_dir, path, transcript)
        gt_path = ground_truth_path(dataset_dir, sample)
        if gt_path.exists():
            try:
                target_count = len(json.loads(gt_path.read_text(encoding="utf-8")))
            except Exception:
                target_count = 0
            samples.append((target_count, sample))
    return [sample for _count, sample in sorted(set(samples))]


def prediction_path(output_dir: Path, sample: str, transcript: str, model_key: str) -> Path:
    return output_dir / f"{sample}_{transcript}_{model_key}_predicted.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_workspace_provenance(
    *,
    workspace: Path,
    output_file: Path,
    sample: str,
    transcript: str,
    model_key: str,
    requested_model: str,
    effort: str,
    dataset_manifest_path: Path,
    runner_source_path: Path,
    runtime_version: str | None,
) -> dict[str, str]:
    provenance = {
        "sample": sample,
        "transcript": transcript,
        "model_key": model_key,
        "requested_model": requested_model,
        "effort": effort,
        "runtime_version": runtime_version or "unknown",
        "output_file": output_file.as_posix(),
        "dataset_manifest_sha256": _sha256_file(dataset_manifest_path),
        "runner_source_sha256": _sha256_file(runner_source_path),
        "transcript_sha256": _sha256_file(workspace / "document_ocr.md"),
        "field_contract_sha256": _sha256_file(workspace / "field_contract.md"),
        "prompt_sha256": _sha256_file(workspace / "prompt.md"),
    }
    encoded = json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode("utf-8")
    provenance["input_fingerprint_sha256"] = hashlib.sha256(encoded).hexdigest()
    return provenance


def _bind_prediction_provenance(provenance: dict[str, str], pred_path: Path) -> dict[str, str]:
    return {**provenance, "prediction_sha256": _sha256_file(pred_path)}


def _resume_metadata_matches(
    metadata: dict | None,
    expected: dict[str, str],
    pred_path: Path,
) -> bool:
    if not isinstance(metadata, dict) or not pred_path.is_file() or pred_path.stat().st_size <= 0:
        return False
    if any(metadata.get(key) != value for key, value in expected.items()):
        return False
    return metadata.get("prediction_sha256") == _sha256_file(pred_path)


def build_incident_contract() -> str:
    return "\n".join(
        [
            "Output JSON shape:",
            '{ "incidents": [ ... ] }',
            "",
            "Extract every claim/loss-run incident record visible in the document.",
            "Every incident must include all fields in the JSON Schema below.",
            "Use empty strings, nulls, empty lists, or 0.0 for unknown values according to the schema.",
            "",
            "JSON Schema:",
            _LOSS_RUN_EXTRACTION_SCHEMA_JSON,
        ]
    )


def build_prompt(output_file: Path) -> str:
    return f"""You are dispatched as a subagent for a specific extraction task; skip superpowers skills.

Your workspace contains:
- document_ocr.md: OCR transcript of one benchmark PDF.
- field_contract.md: the target output shape and allowed fields.

The official ground truth is not present. Do not use files outside this workspace.

Task:
Extract the complete target list from document_ocr.md according to field_contract.md.
Write valid JSON to {output_file.as_posix()}.

You may inspect the document, write temporary scripts, and verify counts. Before finishing:
- Confirm the JSON parses.
- Spot-check beginning, middle, and end records against the OCR.
- Ensure field names match field_contract.md exactly.
- Ensure every target row or target record type requested by the contract is represented.

Do not include explanations in the JSON file.
"""


def prepare_workspace(
    *,
    dataset_dir: Path,
    sample: str,
    transcript: str,
    workspace_root: Path,
) -> tuple[Path, Path, bool]:
    workspace = Path(tempfile.mkdtemp(prefix=f"{sample}_", dir=workspace_root)).resolve()
    (workspace / "output").mkdir(parents=True, exist_ok=True)

    ocr = transcript_path(dataset_dir, sample, transcript).read_text(encoding="utf-8")
    ground_truth = json.loads(ground_truth_path(dataset_dir, sample).read_text(encoding="utf-8"))
    expects_records = uses_record_evaluator(ground_truth)
    output_file = OUTPUT_FILE_RECORDS if expects_records else OUTPUT_FILE_INCIDENTS
    contract = (
        build_record_extraction_contract(ground_truth)
        if expects_records
        else build_incident_contract()
    )

    (workspace / "document_ocr.md").write_text(ocr, encoding="utf-8")
    (workspace / "field_contract.md").write_text(contract, encoding="utf-8")
    (workspace / "prompt.md").write_text(build_prompt(output_file), encoding="utf-8")
    return workspace, output_file, expects_records


def sandbox_profile(repo_root: Path, extra_denied_paths: list[Path] | None = None) -> str:
    denied_paths = {repo_root.resolve()}
    denied_paths.update(path.resolve() for path in extra_denied_paths or [])
    deny_rules = " ".join(
        f'(deny file-read* file-write* (subpath "{path}"))'
        for path in sorted(denied_paths, key=str)
    )
    return f'(version 1) (allow default) {deny_rules}'


def _all_statuses_succeeded(statuses: list[tuple[str, int | str]]) -> bool:
    return bool(statuses) and all(status in (0, "skip", "attest") for _sample, status in statuses)


def _normalize_usage_backed_statuses(
    statuses: list[tuple[str, int | str]],
    sample_metadata: dict[str, dict],
) -> list[tuple[str, int | str]]:
    normalized = []
    for sample, status in statuses:
        metadata = sample_metadata.get(sample) or {}
        if status == "skip" and isinstance(metadata.get("usage"), dict):
            status = 0
        normalized.append((sample, status))
    return normalized


def run_codex(
    workspace: Path,
    repo_root: Path,
    timeout_seconds: int,
    model: str,
    effort: str,
    extra_denied_paths: list[Path] | None = None,
) -> tuple[int | str, str]:
    prompt = (workspace / "prompt.md").read_text(encoding="utf-8")
    cmd = [
        "sandbox-exec",
        "-p",
        sandbox_profile(repo_root, extra_denied_paths),
        "codex",
        "exec",
        "--json",
        "--ephemeral",
        "--skip-git-repo-check",
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{effort}"',
        "--cd",
        str(workspace),
        "--dangerously-bypass-approvals-and-sandbox",
        prompt,
    ]
    env = dict(os.environ)
    env["NO_COLOR"] = "1"
    try:
        completed = subprocess.run(
            cmd,
            cwd="/tmp",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return completed.returncode, completed.stdout
    except subprocess.TimeoutExpired as exc:
        return "timeout", (exc.stdout or "") + f"\nTIMEOUT after {timeout_seconds}s\n"


def load_prediction(workspace: Path, output_file: Path, expects_records: bool) -> list[dict]:
    path = workspace / output_file
    if not path.exists():
        raise FileNotFoundError(f"Agent did not write {output_file.as_posix()}")
    raw_text = path.read_text(encoding="utf-8")
    raw = parse_json_response(raw_text)
    return normalize_record_predictions(raw) if expects_records else _validate_and_normalize_predictions(raw)


def run_sample(
    *,
    dataset_dir: Path,
    repo_root: Path,
    output_dir: Path,
    workspace_root: Path,
    sample: str,
    transcript: str,
    timeout_seconds: int,
    no_resume: bool,
    attest_existing: bool,
    model_key: str,
    model: str,
    effort: str,
    runtime_version: str,
    extra_denied_paths: list[Path],
) -> tuple[str, int | str, dict | None]:
    pred_path = prediction_path(output_dir, sample, transcript, model_key)
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    workspace, output_file, expects_records = prepare_workspace(
        dataset_dir=dataset_dir,
        sample=sample,
        transcript=transcript,
        workspace_root=workspace_root,
    )
    expected_provenance = _build_workspace_provenance(
        workspace=workspace,
        output_file=output_file,
        sample=sample,
        transcript=transcript,
        model_key=model_key,
        requested_model=model,
        effort=effort,
        dataset_manifest_path=dataset_dir / "manifest.json",
        runner_source_path=Path(__file__),
        runtime_version=runtime_version,
    )
    try:
        existing_metadata = _load_run_metadata(output_dir).get(sample)
        if not no_resume and _resume_metadata_matches(
            existing_metadata,
            expected_provenance,
            pred_path,
        ):
            return sample, "skip", existing_metadata

        if not no_resume and attest_existing and pred_path.is_file() and pred_path.stat().st_size > 0:
            log_path = logs_dir / f"{sample}_{transcript}_{model_key}.log"
            if not log_path.is_file():
                return sample, "invalid_attestation: missing Codex log", None
            observed = _parse_codex_log_metadata(
                log_path.read_text(encoding="utf-8"),
                requested_model=model,
                requested_effort=effort,
                runtime_version=runtime_version,
            )
            if observed is None:
                return sample, "invalid_attestation: missing Codex model provenance", None
            if observed["observed_model"] != model or observed["observed_effort"] != effort:
                return sample, "invalid_attestation: Codex model or effort mismatch", None
            if not _cli_versions_match(observed["cli_version"], runtime_version):
                return sample, "invalid_attestation: Codex CLI version mismatch", None
            raw_prediction = json.loads(pred_path.read_text(encoding="utf-8"))
            if expects_records:
                normalize_record_predictions(raw_prediction)
            else:
                _validate_and_normalize_predictions(raw_prediction)
            metadata = {
                **observed,
                **_bind_prediction_provenance(expected_provenance, pred_path),
            }
            return sample, "attest", metadata

        status, log = run_codex(
            workspace,
            repo_root,
            timeout_seconds,
            model,
            effort,
            extra_denied_paths,
        )
        (logs_dir / f"{sample}_{transcript}_{model_key}.log").write_text(
            log,
            encoding="utf-8",
        )
        if status == 0:
            observed = _parse_codex_log_metadata(
                log,
                requested_model=model,
                requested_effort=effort,
                runtime_version=runtime_version,
            )
            if observed is None:
                return sample, "invalid_result: missing Codex model provenance", None
            if observed["observed_model"] != model or observed["observed_effort"] != effort:
                return (
                    sample,
                    "invalid_result: requested model or effort did not match Codex log",
                    None,
                )
            if not _cli_versions_match(observed["cli_version"], runtime_version):
                return sample, "invalid_result: Codex CLI version mismatch", None
            predicted = load_prediction(workspace, output_file, expects_records)
            pred_path.write_text(json.dumps(predicted, indent=2), encoding="utf-8")
            metadata = {
                **observed,
                **_bind_prediction_provenance(expected_provenance, pred_path),
            }
            return sample, status, metadata
        return sample, status, None
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _codex_cli_version() -> str | None:
    try:
        return subprocess.check_output(
            ["codex", "--version"],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _parse_codex_log_header(log: str) -> dict[str, str] | None:
    version = re.search(r"^OpenAI Codex\s+(.+)$", log, flags=re.MULTILINE)
    model = re.search(r"^model:\s*(.+)$", log, flags=re.MULTILINE)
    effort = re.search(r"^reasoning effort:\s*(.+)$", log, flags=re.MULTILINE)
    if not (version and model and effort):
        return None
    return {
        "cli_version": version.group(1).strip(),
        "observed_model": model.group(1).strip(),
        "observed_effort": effort.group(1).strip(),
    }


_CODEX_USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)


def _parse_codex_json_metadata(
    log: str,
    *,
    requested_model: str,
    requested_effort: str,
    runtime_version: str,
) -> dict | None:
    usage = {key: 0 for key in _CODEX_USAGE_KEYS}
    thread_id = None
    completed_turn_count = 0
    for line in log.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
        if event.get("type") != "turn.completed":
            continue
        turn_usage = event.get("usage")
        if not isinstance(turn_usage, dict):
            continue
        completed_turn_count += 1
        for key in _CODEX_USAGE_KEYS:
            value = turn_usage.get(key, 0)
            if isinstance(value, int) and value >= 0:
                usage[key] += value

    if completed_turn_count == 0:
        return None
    metadata = {
        "cli_version": runtime_version,
        "observed_model": requested_model,
        "observed_effort": requested_effort,
        "provenance_source": "codex_json_events_and_invocation",
        "completed_turn_count": completed_turn_count,
        "usage": usage,
    }
    if isinstance(thread_id, str) and thread_id:
        metadata["thread_id"] = thread_id
    return metadata


def _parse_codex_log_metadata(
    log: str,
    *,
    requested_model: str,
    requested_effort: str,
    runtime_version: str,
) -> dict | None:
    return _parse_codex_log_header(log) or _parse_codex_json_metadata(
        log,
        requested_model=requested_model,
        requested_effort=requested_effort,
        runtime_version=runtime_version,
    )


def _cli_versions_match(observed: str, runtime: str) -> bool:
    observed_number = re.search(r"\d+(?:\.\d+)+", observed)
    runtime_number = re.search(r"\d+(?:\.\d+)+", runtime)
    return bool(
        observed_number
        and runtime_number
        and observed_number.group(0) == runtime_number.group(0)
    )


def _audit_codex_log_headers(
    output_dir: Path,
    transcript: str,
    model_key: str,
    *,
    requested_model: str,
    requested_effort: str,
    runtime_version: str,
) -> dict[str, dict]:
    logs_dir = output_dir / "logs"
    suffix = f"_{transcript}_{model_key}.log"
    audit: dict[str, dict] = {}
    if not logs_dir.exists():
        return audit
    for path in sorted(logs_dir.glob(f"*{suffix}")):
        header = _parse_codex_log_metadata(
            path.read_text(encoding="utf-8"),
            requested_model=requested_model,
            requested_effort=requested_effort,
            runtime_version=runtime_version,
        )
        if header is not None:
            audit[path.name.removesuffix(suffix)] = header
    return audit


def _aggregate_codex_usage(samples: dict[str, dict]) -> dict | None:
    totals = {key: 0 for key in _CODEX_USAGE_KEYS}
    measured_sample_count = 0
    for metadata in samples.values():
        usage = metadata.get("usage")
        if not isinstance(usage, dict):
            continue
        measured_sample_count += 1
        for key in _CODEX_USAGE_KEYS:
            value = usage.get(key, 0)
            if isinstance(value, int) and value >= 0:
                totals[key] += value
    if measured_sample_count == 0:
        return None
    return {
        "measured_sample_count": measured_sample_count,
        **totals,
    }


def _load_run_metadata(output_dir: Path) -> dict:
    path = output_dir / RUN_METADATA_FILE
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload.get("samples") or {}


def _metadata_denied_path_labels(
    repo_root: Path,
    denied_paths: list[Path] | None,
) -> list[str]:
    """Describe sandbox deny paths without serializing host-specific locations."""
    resolved_repo = repo_root.resolve()
    resolved_repo_parent = resolved_repo.parent
    resolved_home = Path.home().resolve()
    known_paths = {
        resolved_repo: "<repo-root>",
        resolved_repo_parent: "<repo-parent>",
        resolved_home: "<user-home>",
        (resolved_home / "Desktop").resolve(): "<user-home>/Desktop",
    }

    labels: list[str] = []
    for index, path in enumerate(denied_paths or [], start=1):
        resolved_path = path.resolve()
        labels.append(known_paths.get(resolved_path, f"<denied-path-{index}>"))
    return labels


def _write_run_metadata(
    *,
    repo_root: Path,
    output_dir: Path,
    transcript: str,
    model_key: str,
    requested_model: str,
    effort: str,
    statuses: list[tuple[str, int | str]],
    sample_metadata: dict[str, dict] | None = None,
    runtime_version: str | None = None,
    extra_denied_paths: list[Path] | None = None,
) -> None:
    effective_runtime_version = runtime_version or _codex_cli_version() or "unknown"
    observed = _audit_codex_log_headers(
        output_dir,
        transcript,
        model_key,
        requested_model=requested_model,
        requested_effort=effort,
        runtime_version=effective_runtime_version,
    )
    for sample, metadata in (sample_metadata or {}).items():
        observed[sample] = {**observed.get(sample, {}), **metadata}
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runner": Path(__file__).name,
        "model_key": model_key,
        "requested_model": requested_model,
        "effort": effort,
        "transcript": transcript,
        "cli_version_observed_at_metadata_write": effective_runtime_version,
        "authentication": "Codex subscription; credentials are not stored",
        "additional_denied_paths": _metadata_denied_path_labels(
            repo_root,
            extra_denied_paths,
        ),
        "sample_statuses": {sample: status for sample, status in statuses},
        "samples": observed,
    }
    usage_totals = _aggregate_codex_usage(observed)
    if usage_totals is not None:
        payload["usage_totals"] = usage_totals
    (output_dir / RUN_METADATA_FILE).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repository-denied Codex CLI extraction")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--transcript", default="ocr", choices=["ocr", "canonical"])
    parser.add_argument("--samples", nargs="+", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--workspace-root", default="/tmp/longlistbench-codex-workspaces")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--attest-existing",
        action="store_true",
        help="Attest legacy predictions only when their saved CLI logs match the requested model and effort",
    )
    parser.add_argument("--workers", type=int, default=1, help="Number of samples to run in parallel")
    parser.add_argument("--model-key", default=DEFAULT_MODEL_KEY, help="Offline scorer model key")
    parser.add_argument("--model", default=DEFAULT_CODEX_MODEL, help="Codex model slug")
    parser.add_argument("--effort", default=DEFAULT_REASONING_EFFORT, help="Codex reasoning effort")
    parser.add_argument(
        "--deny-path",
        action="append",
        default=[],
        help="Additional host path to deny to the Codex process; may be repeated",
    )
    args = parser.parse_args()

    if shutil.which("sandbox-exec") is None:
        raise SystemExit("sandbox-exec is required for repository-denied Codex CLI runs")
    if args.model_key not in MODELS:
        raise SystemExit(f"Unknown offline scorer model key: {args.model_key}")
    runtime_version = _codex_cli_version()
    if not runtime_version:
        raise SystemExit("Unable to determine Codex CLI version")

    repo_root = Path(__file__).resolve().parents[1]
    dataset_dir = default_dataset_dir()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace_root = Path(args.workspace_root)
    workspace_root.mkdir(parents=True, exist_ok=True)
    extra_denied_paths = [Path(path) for path in args.deny_path]

    samples = discover_samples(dataset_dir, args.transcript, args.samples)
    statuses: list[tuple[str, int | str]] = []
    sample_metadata = _load_run_metadata(output_dir)
    worker_count = max(1, args.workers)
    if worker_count == 1:
        for index, sample in enumerate(samples, start=1):
            print(f"[{index}/{len(samples)}] {args.model_key} {sample}", flush=True)
            sample_id, status, metadata = run_sample(
                dataset_dir=dataset_dir,
                repo_root=repo_root,
                output_dir=output_dir,
                workspace_root=workspace_root,
                sample=sample,
                transcript=args.transcript,
                timeout_seconds=args.timeout_seconds,
                no_resume=args.no_resume,
                attest_existing=args.attest_existing,
                model_key=args.model_key,
                model=args.model,
                effort=args.effort,
                runtime_version=runtime_version,
                extra_denied_paths=extra_denied_paths,
            )
            statuses.append((sample_id, status))
            if metadata is not None:
                sample_metadata[sample_id] = metadata
            print(f"  -> {status}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=min(worker_count, len(samples) or 1)) as executor:
            future_to_sample = {}
            for index, sample in enumerate(samples, start=1):
                print(f"[{index}/{len(samples)}] {args.model_key} {sample} QUEUED", flush=True)
                future = executor.submit(
                    run_sample,
                    dataset_dir=dataset_dir,
                    repo_root=repo_root,
                    output_dir=output_dir,
                    workspace_root=workspace_root,
                    sample=sample,
                    transcript=args.transcript,
                    timeout_seconds=args.timeout_seconds,
                    no_resume=args.no_resume,
                    attest_existing=args.attest_existing,
                    model_key=args.model_key,
                    model=args.model,
                    effort=args.effort,
                    runtime_version=runtime_version,
                    extra_denied_paths=extra_denied_paths,
                )
                future_to_sample[future] = sample

            for future in as_completed(future_to_sample):
                sample = future_to_sample[future]
                try:
                    sample_id, status, metadata = future.result()
                except Exception as exc:
                    sample_id, status, metadata = sample, f"error: {exc}", None
                statuses.append((sample_id, status))
                if metadata is not None:
                    sample_metadata[sample_id] = metadata
                print(f"[DONE] {args.model_key} {sample_id} -> {status}", flush=True)

        status_order = {sample: index for index, sample in enumerate(samples)}
        statuses.sort(key=lambda item: status_order.get(item[0], len(status_order)))

    statuses = _normalize_usage_backed_statuses(statuses, sample_metadata)
    (output_dir / "per_sample_status.tsv").write_text(
        "sample\tstatus\n" + "\n".join(f"{sample}\t{status}" for sample, status in statuses) + "\n",
        encoding="utf-8",
    )
    _write_run_metadata(
        repo_root=repo_root,
        output_dir=output_dir,
        transcript=args.transcript,
        model_key=args.model_key,
        requested_model=args.model,
        effort=args.effort,
        statuses=statuses,
        sample_metadata=sample_metadata,
        runtime_version=runtime_version,
        extra_denied_paths=extra_denied_paths,
    )
    results = run_evaluation_from_saved_predictions(
        models=[args.model_key],
        samples=args.samples,
        transcripts=[args.transcript],
        output_dir=output_dir,
    )
    generate_report(results, output_dir)
    return 0 if _all_statuses_succeeded(statuses) else 1


if __name__ == "__main__":
    raise SystemExit(main())
