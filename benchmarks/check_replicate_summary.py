#!/usr/bin/env python3
"""Verify repeated full-corpus runs and their aggregate summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"
DEFAULT_SUMMARIES = (
    REPO_ROOT
    / "benchmarks/cost_measurements/gpt56_sol_replicates_20260802/summary.json",
    REPO_ROOT
    / "benchmarks/cost_measurements/gpt56_terra_replicates_20260801/summary.json",
    REPO_ROOT
    / "benchmarks/cost_measurements/gpt56_luna_replicates_20260801/summary.json",
)
REPORT_METRICS = {
    "exact_record_recall": "exact_record_recall",
    "exact_record_precision": "exact_record_precision",
    "exact_record_f1": "exact_record_f1",
    "complete_documents": "complete_documents",
    "field_micro_f1": "weighted_f1",
    "field_macro_f1": "avg_f1",
    "predicted_records": "total_pred_rows",
    "execution_errors": "errors",
}
USAGE_METRICS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _close(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return abs(left - right) <= tolerance


def _append_mismatch(
    errors: list[str], label: str, expected: Any, actual: Any
) -> None:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if _close(float(expected), float(actual)):
            return
    elif expected == actual:
        return
    errors.append(f"{label}: summary={expected!r}, artifact={actual!r}")


def _verify_report_replay(result_dir: Path) -> str | None:
    command = [
        sys.executable,
        str(REPO_ROOT / "benchmarks/check_evaluation_report.py"),
        "--results-dir",
        str(result_dir),
        "--require-full-corpus",
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return None
    output = (completed.stdout + completed.stderr).strip()
    return f"{result_dir.name}: report replay failed: {output}"


def verify_summary(summary_path: Path, *, replay_reports: bool = True) -> list[str]:
    summary = _load(summary_path)
    errors: list[str] = []
    runs = summary.get("runs") or []
    model = str(summary.get("model"))
    protocol = summary.get("execution_protocol")

    if summary.get("schema_version") != 2:
        errors.append(f"{summary_path}: expected schema_version 2")
    if summary.get("run_count") != len(runs) or len(runs) < 2:
        errors.append(f"{summary_path}: run_count does not match runs")
    if summary.get("selection_policy") != {
        "leaderboard_statistic": "arithmetic_mean",
        "variability_statistic": "sample_standard_deviation",
        "preselected_reference_run": "run_1",
        "best_of_n_selection": False,
    }:
        errors.append(f"{summary_path}: unexpected reporting policy")

    fingerprint_sets: list[dict[str, tuple[str, ...]]] = []
    for run in runs:
        run_id = str(run.get("id"))
        result_dir = RESULTS_DIR / str(run.get("result_dir"))
        report_path = result_dir / "evaluation_report.json"
        metadata_path = result_dir / "run_metadata.json"
        required_paths = (
            report_path,
            result_dir / "evaluation_report.md",
            metadata_path,
            result_dir / "per_sample_status.tsv",
            result_dir / "README.md",
        )
        for path in required_paths:
            if not path.is_file():
                errors.append(f"{run_id}: missing {path}")
        if not report_path.is_file() or not metadata_path.is_file():
            continue

        report = _load(report_path)
        metadata = _load(metadata_path)
        model_key = str(metadata.get("model_key"))
        stats = (report.get("model_stats") or {}).get(model_key)
        samples = metadata.get("samples") or {}
        if not isinstance(stats, dict):
            errors.append(f"{run_id}: report missing model_stats[{model_key!r}]")
            continue

        _append_mismatch(errors, f"{run_id}.report_sha256", run.get("report_sha256"), _sha256(report_path))
        _append_mismatch(errors, f"{run_id}.replicate_id", run_id, metadata.get("replicate_id"))
        _append_mismatch(errors, f"{run_id}.model", model, metadata.get("requested_model"))
        _append_mismatch(errors, f"{run_id}.effort", summary.get("reasoning_effort"), metadata.get("effort"))
        _append_mismatch(errors, f"{run_id}.transcript", summary.get("input_condition"), metadata.get("transcript"))
        _append_mismatch(errors, f"{run_id}.runtime", summary.get("runtime"), metadata.get("cli_version_observed_at_metadata_write"))
        _append_mismatch(errors, f"{run_id}.generated_at", run.get("generated_at"), metadata.get("generated_at"))
        _append_mismatch(errors, f"{run_id}.report_timestamp", run.get("report_timestamp"), report.get("timestamp"))
        _append_mismatch(errors, f"{run_id}.protocol", protocol, metadata.get("execution_protocol"))
        _append_mismatch(errors, f"{run_id}.sample_count", summary["dataset"]["documents"], len(samples))
        _append_mismatch(errors, f"{run_id}.manifest", summary["dataset"]["manifest_sha256"], (report.get("dataset") or {}).get("manifest_sha256"))

        statuses = metadata.get("sample_statuses") or {}
        if len(statuses) != summary["dataset"]["documents"] or any(
            status != 0 for status in statuses.values()
        ):
            errors.append(f"{run_id}: sample statuses are incomplete or nonzero")

        for summary_key, report_key in REPORT_METRICS.items():
            _append_mismatch(
                errors,
                f"{run_id}.{summary_key}",
                run.get(summary_key),
                stats.get(report_key),
            )

        usage = metadata.get("usage_totals") or {}
        for key in USAGE_METRICS:
            _append_mismatch(errors, f"{run_id}.{key}", run.get(key), usage.get(key))
        uncached = (
            int(usage.get("input_tokens", 0))
            - int(usage.get("cached_input_tokens", 0))
            - int(usage.get("cache_write_input_tokens", 0))
        )
        _append_mismatch(errors, f"{run_id}.uncached_input_tokens", run.get("uncached_input_tokens"), uncached)

        credit_rates = summary["pricing"]["chatgpt_credits_per_million_tokens"]
        api_rates = summary["pricing"]["api_usd_per_million_tokens"]
        credits = (
            uncached * credit_rates["uncached_input"]
            + usage["cached_input_tokens"] * credit_rates["cached_input"]
            + usage["output_tokens"] * credit_rates["output"]
        ) / 1_000_000
        api_cost = (
            uncached * api_rates["uncached_input"]
            + usage["cached_input_tokens"] * api_rates["cached_input"]
            + usage["cache_write_input_tokens"] * api_rates["cache_write_input"]
            + usage["output_tokens"] * api_rates["output"]
        ) / 1_000_000
        _append_mismatch(errors, f"{run_id}.chatgpt_credits", run.get("chatgpt_credits"), credits)
        _append_mismatch(errors, f"{run_id}.api_equivalent_usd", run.get("api_equivalent_usd"), api_cost)

        fingerprints: dict[str, tuple[str, ...]] = {}
        for sample, sample_metadata in samples.items():
            prediction_path = result_dir / (
                f"{sample}_{metadata['transcript']}_{model_key}_predicted.json"
            )
            if not prediction_path.is_file():
                errors.append(f"{run_id}: missing prediction {prediction_path.name}")
                continue
            _append_mismatch(
                errors,
                f"{run_id}.{sample}.prediction_sha256",
                sample_metadata.get("prediction_sha256"),
                _sha256(prediction_path),
            )
            fingerprints[sample] = tuple(
                str(sample_metadata.get(key))
                for key in (
                    "transcript_sha256",
                    "field_contract_sha256",
                    "prompt_sha256",
                    "input_fingerprint_sha256",
                )
            )
        fingerprint_sets.append(fingerprints)

        if replay_reports:
            replay_error = _verify_report_replay(result_dir)
            if replay_error:
                errors.append(replay_error)

    if fingerprint_sets and any(
        fingerprints != fingerprint_sets[0] for fingerprints in fingerprint_sets[1:]
    ):
        errors.append(f"{summary_path}: input fingerprints differ across runs")

    aggregates = summary.get("aggregate") or {}
    for metric, expected in aggregates.items():
        values = [run[metric] for run in runs]
        computed = {
            "median": median(values),
            "mean": mean(values),
            "min": min(values),
            "max": max(values),
            "sample_standard_deviation": stdev(values),
        }
        for statistic, actual in computed.items():
            _append_mismatch(
                errors,
                f"aggregate.{metric}.{statistic}",
                expected.get(statistic),
                actual,
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("summaries", nargs="*", type=Path)
    parser.add_argument(
        "--skip-report-replay",
        action="store_true",
        help="Validate package metadata and aggregates without rescoring predictions",
    )
    args = parser.parse_args()
    summaries = tuple(args.summaries) or DEFAULT_SUMMARIES
    errors = [
        error
        for summary in summaries
        for error in verify_summary(
            summary,
            replay_reports=not args.skip_report_replay,
        )
    ]
    if errors:
        print("Replicate verification failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: verified {len(summaries)} summaries and their full run packages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
