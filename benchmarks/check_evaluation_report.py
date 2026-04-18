import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

_SCRIPT_DIR = Path(__file__).parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from models.loss_run import FinancialBreakdown, LossRunIncident
try:
    from .evaluation_metrics import evaluate_extraction
except ImportError:
    from evaluation_metrics import evaluate_extraction


_LOSS_RUN_FIELDS = set(LossRunIncident.model_fields.keys())
_BREAKDOWN_FIELDS = set(FinancialBreakdown.model_fields.keys())
_BREAKDOWN_KEYS = {"bi", "pd", "lae", "ded"}


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
    # Prediction files are stored as a list of incidents.
    if not isinstance(raw, list):
        raise ValueError("Predicted output must be a JSON list of incidents")

    normalized: list[dict] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Incident at index {idx} must be an object")
        _validate_incident_dict_is_complete(item)
        try:
            obj = LossRunIncident.model_validate(item)
        except ValidationError as e:
            raise ValueError(f"Incident at index {idx} failed schema validation: {e}") from e
        normalized.append(obj.model_dump(mode="json"))

    return normalized


def _is_close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def _compare_metrics(
    *,
    sample: str,
    model: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
    tol: float,
) -> list[str]:
    errors: list[str] = []

    for key, expected_value in expected.items():
        if key not in actual:
            errors.append(f"{sample} / {model}: missing key '{key}' in recomputed metrics")
            continue

        actual_value = actual[key]

        if key in {"recall", "precision", "f1"}:
            if not _is_close(float(expected_value), float(actual_value), tol):
                errors.append(
                    f"{sample} / {model}: {key} mismatch (report={expected_value!r}, recomputed={actual_value!r})"
                )
            continue

        if key in {"missing_ids", "extra_ids"}:
            if list(expected_value) != list(actual_value):
                errors.append(
                    f"{sample} / {model}: {key} mismatch (report={expected_value!r}, recomputed={actual_value!r})"
                )
            continue

        if expected_value != actual_value:
            errors.append(
                f"{sample} / {model}: {key} mismatch (report={expected_value!r}, recomputed={actual_value!r})"
            )

    return errors


def _recompute_model_stats(detailed_results: list[dict[str, Any]]) -> dict[str, Any]:
    model_stats: dict[str, Any] = {}

    for r in detailed_results:
        model = r["model"]
        tier = r["tier"]
        fmt = r["format"]
        transcript = r.get("transcript", "ocr")
        metrics = r.get("metrics") or {}
        error = r.get("error")

        if model not in model_stats:
            model_stats[model] = {
                "total_samples": 0,
                "total_f1": 0.0,
                "total_recall": 0.0,
                "total_precision": 0.0,
                "total_found": 0,
                "total_gold_field_pairs": 0,
                "total_pred_field_pairs": 0,
                "total_rows": 0,
                "errors": 0,
                "by_tier": {},
                "by_format": {},
                "by_transcript": {},
            }

        stats = model_stats[model]
        stats["total_samples"] += 1
        stats["total_f1"] += float(metrics.get("f1", 0.0))
        stats["total_recall"] += float(metrics.get("recall", 0.0))
        stats["total_precision"] += float(metrics.get("precision", 0.0))
        stats["total_found"] += int(metrics.get("found", 0))
        stats["total_gold_field_pairs"] += int(metrics.get("total_gold_field_pairs", 0))
        stats["total_pred_field_pairs"] += int(metrics.get("total_pred_field_pairs", 0))
        stats["total_rows"] += int(metrics.get("ground_truth_count", 0))
        if error:
            stats["errors"] += 1

        if tier not in stats["by_tier"]:
            stats["by_tier"][tier] = {
                "count": 0,
                "rows": 0,
                "f1_sum": 0.0,
                "recall_sum": 0.0,
                "found_sum": 0,
                "gold_pairs_sum": 0,
                "pred_pairs_sum": 0,
            }
        stats["by_tier"][tier]["count"] += 1
        stats["by_tier"][tier]["rows"] += int(metrics.get("ground_truth_count", 0))
        stats["by_tier"][tier]["f1_sum"] += float(metrics.get("f1", 0.0))
        stats["by_tier"][tier]["recall_sum"] += float(metrics.get("recall", 0.0))
        stats["by_tier"][tier]["found_sum"] += int(metrics.get("found", 0))
        stats["by_tier"][tier]["gold_pairs_sum"] += int(metrics.get("total_gold_field_pairs", 0))
        stats["by_tier"][tier]["pred_pairs_sum"] += int(metrics.get("total_pred_field_pairs", 0))

        if fmt not in stats["by_format"]:
            stats["by_format"][fmt] = {
                "count": 0,
                "rows": 0,
                "f1_sum": 0.0,
                "recall_sum": 0.0,
                "found_sum": 0,
                "gold_pairs_sum": 0,
                "pred_pairs_sum": 0,
            }
        stats["by_format"][fmt]["count"] += 1
        stats["by_format"][fmt]["rows"] += int(metrics.get("ground_truth_count", 0))
        stats["by_format"][fmt]["f1_sum"] += float(metrics.get("f1", 0.0))
        stats["by_format"][fmt]["recall_sum"] += float(metrics.get("recall", 0.0))
        stats["by_format"][fmt]["found_sum"] += int(metrics.get("found", 0))
        stats["by_format"][fmt]["gold_pairs_sum"] += int(metrics.get("total_gold_field_pairs", 0))
        stats["by_format"][fmt]["pred_pairs_sum"] += int(metrics.get("total_pred_field_pairs", 0))

        if transcript not in stats["by_transcript"]:
            stats["by_transcript"][transcript] = {
                "count": 0,
                "rows": 0,
                "f1_sum": 0.0,
                "recall_sum": 0.0,
                "found_sum": 0,
                "gold_pairs_sum": 0,
                "pred_pairs_sum": 0,
            }
        stats["by_transcript"][transcript]["count"] += 1
        stats["by_transcript"][transcript]["rows"] += int(metrics.get("ground_truth_count", 0))
        stats["by_transcript"][transcript]["f1_sum"] += float(metrics.get("f1", 0.0))
        stats["by_transcript"][transcript]["recall_sum"] += float(metrics.get("recall", 0.0))
        stats["by_transcript"][transcript]["found_sum"] += int(metrics.get("found", 0))
        stats["by_transcript"][transcript]["gold_pairs_sum"] += int(metrics.get("total_gold_field_pairs", 0))
        stats["by_transcript"][transcript]["pred_pairs_sum"] += int(metrics.get("total_pred_field_pairs", 0))

    for stats in model_stats.values():
        n = stats["total_samples"]
        stats["avg_f1"] = stats["total_f1"] / n if n > 0 else 0.0
        stats["avg_recall"] = stats["total_recall"] / n if n > 0 else 0.0
        stats["avg_precision"] = stats["total_precision"] / n if n > 0 else 0.0
        total_found = stats["total_found"]
        total_gold = stats["total_gold_field_pairs"]
        total_pred = stats["total_pred_field_pairs"]
        stats["weighted_recall"] = total_found / total_gold if total_gold > 0 else 0.0
        stats["weighted_precision"] = total_found / total_pred if total_pred > 0 else 0.0
        stats["weighted_f1"] = (
            2 * stats["weighted_precision"] * stats["weighted_recall"] / (stats["weighted_precision"] + stats["weighted_recall"])
            if (stats["weighted_precision"] + stats["weighted_recall"]) > 0 else 0.0
        )

        for tier_stats in stats["by_tier"].values():
            c = tier_stats["count"]
            tier_stats["avg_f1"] = tier_stats["f1_sum"] / c if c > 0 else 0.0
            tier_stats["avg_recall"] = tier_stats["recall_sum"] / c if c > 0 else 0.0
            gold_pairs = tier_stats["gold_pairs_sum"]
            pred_pairs = tier_stats["pred_pairs_sum"]
            found_sum = tier_stats["found_sum"]
            tier_stats["weighted_recall"] = found_sum / gold_pairs if gold_pairs > 0 else 0.0
            tier_stats["weighted_precision"] = found_sum / pred_pairs if pred_pairs > 0 else 0.0
            tier_stats["weighted_f1"] = (
                2 * tier_stats["weighted_precision"] * tier_stats["weighted_recall"] / (tier_stats["weighted_precision"] + tier_stats["weighted_recall"])
                if (tier_stats["weighted_precision"] + tier_stats["weighted_recall"]) > 0 else 0.0
            )

        for fmt_stats in stats["by_format"].values():
            c = fmt_stats["count"]
            fmt_stats["avg_f1"] = fmt_stats["f1_sum"] / c if c > 0 else 0.0
            fmt_stats["avg_recall"] = fmt_stats["recall_sum"] / c if c > 0 else 0.0
            gold_pairs = fmt_stats["gold_pairs_sum"]
            pred_pairs = fmt_stats["pred_pairs_sum"]
            found_sum = fmt_stats["found_sum"]
            fmt_stats["weighted_recall"] = found_sum / gold_pairs if gold_pairs > 0 else 0.0
            fmt_stats["weighted_precision"] = found_sum / pred_pairs if pred_pairs > 0 else 0.0
            fmt_stats["weighted_f1"] = (
                2 * fmt_stats["weighted_precision"] * fmt_stats["weighted_recall"] / (fmt_stats["weighted_precision"] + fmt_stats["weighted_recall"])
                if (fmt_stats["weighted_precision"] + fmt_stats["weighted_recall"]) > 0 else 0.0
            )

        for transcript_stats in stats["by_transcript"].values():
            c = transcript_stats["count"]
            transcript_stats["avg_f1"] = transcript_stats["f1_sum"] / c if c > 0 else 0.0
            transcript_stats["avg_recall"] = transcript_stats["recall_sum"] / c if c > 0 else 0.0
            gold_pairs = transcript_stats["gold_pairs_sum"]
            pred_pairs = transcript_stats["pred_pairs_sum"]
            found_sum = transcript_stats["found_sum"]
            transcript_stats["weighted_recall"] = found_sum / gold_pairs if gold_pairs > 0 else 0.0
            transcript_stats["weighted_precision"] = found_sum / pred_pairs if pred_pairs > 0 else 0.0
            transcript_stats["weighted_f1"] = (
                2 * transcript_stats["weighted_precision"] * transcript_stats["weighted_recall"] / (transcript_stats["weighted_precision"] + transcript_stats["weighted_recall"])
                if (transcript_stats["weighted_precision"] + transcript_stats["weighted_recall"]) > 0 else 0.0
            )

    return model_stats


def _compare_model_stats(
    *,
    expected: dict[str, Any],
    actual: dict[str, Any],
    tol: float,
) -> list[str]:
    errors: list[str] = []

    expected_models = set(expected.keys())
    actual_models = set(actual.keys())

    missing = expected_models - actual_models
    extra = actual_models - expected_models
    if missing:
        errors.append(f"model_stats missing models: {sorted(missing)}")
    if extra:
        errors.append(f"model_stats has unexpected models: {sorted(extra)}")

    for model in sorted(expected_models & actual_models):
        e = expected[model]
        a = actual[model]

        for key in [
            "total_samples",
            "errors",
            "total_f1",
            "total_recall",
            "total_precision",
            "total_found",
            "total_gold_field_pairs",
            "total_pred_field_pairs",
            "total_rows",
            "avg_f1",
            "avg_recall",
            "avg_precision",
            "weighted_f1",
            "weighted_recall",
            "weighted_precision",
        ]:
            if key not in a:
                errors.append(f"model_stats[{model}] missing key '{key}'")
                continue

            ev = e[key]
            av = a[key]

            if isinstance(ev, float) or isinstance(av, float):
                if not _is_close(float(ev), float(av), tol):
                    errors.append(
                        f"model_stats[{model}].{key} mismatch (report={ev!r}, recomputed={av!r})"
                    )
            else:
                if ev != av:
                    errors.append(
                        f"model_stats[{model}].{key} mismatch (report={ev!r}, recomputed={av!r})"
                    )

        for group_key in ["by_tier", "by_format", "by_transcript"]:
            if group_key == "by_transcript" and group_key not in e:
                continue
            e_group = e.get(group_key) or {}
            a_group = a.get(group_key) or {}

            if set(e_group.keys()) != set(a_group.keys()):
                errors.append(
                    f"model_stats[{model}].{group_key} keys mismatch (report={sorted(e_group.keys())}, recomputed={sorted(a_group.keys())})"
                )
                continue

            for k, e_stats in e_group.items():
                a_stats = a_group[k]
                for stat_key in [
                    "count",
                    "rows",
                    "f1_sum",
                    "recall_sum",
                    "found_sum",
                    "gold_pairs_sum",
                    "pred_pairs_sum",
                    "avg_f1",
                    "avg_recall",
                    "weighted_f1",
                    "weighted_recall",
                    "weighted_precision",
                ]:
                    if stat_key not in a_stats:
                        errors.append(
                            f"model_stats[{model}].{group_key}[{k}] missing key '{stat_key}'"
                        )
                        continue

                    ev = e_stats[stat_key]
                    av = a_stats[stat_key]
                    if isinstance(ev, float) or isinstance(av, float):
                        if not _is_close(float(ev), float(av), tol):
                            errors.append(
                                f"model_stats[{model}].{group_key}[{k}].{stat_key} mismatch (report={ev!r}, recomputed={av!r})"
                            )
                    else:
                        if ev != av:
                            errors.append(
                                f"model_stats[{model}].{group_key}[{k}].{stat_key} mismatch (report={ev!r}, recomputed={av!r})"
                            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--claims-dir",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--report-json",
        type=str,
        default=None,
    )
    parser.add_argument("--tolerance", type=float, default=1e-12)

    args = parser.parse_args()

    script_dir = Path(__file__).parent
    claims_dir = Path(args.claims_dir) if args.claims_dir else (script_dir / "claims")
    default_results_dir = script_dir / "results" / "scratch"
    if not default_results_dir.exists():
        default_results_dir = script_dir / "results"
    results_dir = Path(args.results_dir) if args.results_dir else default_results_dir
    report_json = Path(args.report_json) if args.report_json else (results_dir / "evaluation_report.json")

    errors: list[str] = []

    if not report_json.exists():
        print(f"Missing report: {report_json}")
        return 2

    report = json.loads(report_json.read_text(encoding="utf-8"))

    detailed_results = report.get("detailed_results")
    model_stats = report.get("model_stats")

    if not isinstance(detailed_results, list):
        print("Invalid report: missing detailed_results")
        return 2
    if not isinstance(model_stats, dict):
        print("Invalid report: missing model_stats")
        return 2

    for entry in detailed_results:
        model = entry["model"]
        sample = entry["sample"]
        transcript = entry.get("transcript", "ocr")

        if entry.get("error"):
            errors.append(f"{sample} [{transcript}] / {model}: report has error entry: {entry['error']}")
            continue

        pred_path = results_dir / f"{sample}_{transcript}_{model}_predicted.json"
        legacy_pred_path = results_dir / f"{sample}_{model}_predicted.json" if transcript == "ocr" else None
        if not pred_path.exists() and legacy_pred_path is not None and legacy_pred_path.exists():
            pred_path = legacy_pred_path
        if not pred_path.exists():
            errors.append(f"{sample} [{transcript}] / {model}: missing predicted file {pred_path}")
            continue

        gt_path = claims_dir / f"{sample}.json"
        if not gt_path.exists():
            errors.append(f"{sample} [{transcript}] / {model}: missing ground truth file {gt_path}")
            continue

        predicted_raw = json.loads(pred_path.read_text(encoding="utf-8"))
        try:
            predicted = _validate_and_normalize_predictions(predicted_raw)
        except Exception as e:
            errors.append(f"{sample} [{transcript}] / {model}: predicted output failed schema validation: {e}")
            continue
        ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))

        actual_metrics = evaluate_extraction(predicted, ground_truth)
        expected_metrics = entry.get("metrics") or {}

        errors.extend(
            _compare_metrics(
                sample=sample,
                model=model,
                expected=expected_metrics,
                actual=actual_metrics,
                tol=args.tolerance,
            )
        )

    recomputed_model_stats = _recompute_model_stats(detailed_results)
    errors.extend(
        _compare_model_stats(
            expected=model_stats,
            actual=recomputed_model_stats,
            tol=args.tolerance,
        )
    )

    if errors:
        print("Report check failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("OK: evaluation_report.json matches saved predictions + golden data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
