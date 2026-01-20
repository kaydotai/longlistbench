import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import ValidationError

_SCRIPT_DIR = Path(__file__).parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from models.loss_run import FinancialBreakdown, LossRunIncident


def normalize_incident_number(incident_num: str) -> str:
    if not incident_num:
        return ""
    incident_num = str(incident_num).strip()
    for prefix in ["Incident #", "Incident#", "Incident ", "#", "INC"]:
        if incident_num.startswith(prefix):
            incident_num = incident_num[len(prefix):]
    return incident_num.strip()


def evaluate_extraction(predicted: list[dict], ground_truth: list[dict]) -> dict[str, Any]:
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
                        f"{incident_id}|{k}.{kk}|{json.dumps(vv, sort_keys=True, separators=(',', ':'))}"
                    )
            else:
                pairs.append(
                    f"{incident_id}|{k}|{json.dumps(v, sort_keys=True, separators=(',', ':'))}"
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
        exact_record_matches += sum(
            (Counter(gt_by_id.get(inc, [])) & Counter(pred_by_id.get(inc, []))).values()
        )

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
        metrics = r.get("metrics") or {}
        error = r.get("error")

        if model not in model_stats:
            model_stats[model] = {
                "total_samples": 0,
                "total_f1": 0.0,
                "total_recall": 0.0,
                "total_precision": 0.0,
                "errors": 0,
                "by_tier": {},
                "by_format": {},
            }

        stats = model_stats[model]
        stats["total_samples"] += 1
        stats["total_f1"] += float(metrics.get("f1", 0.0))
        stats["total_recall"] += float(metrics.get("recall", 0.0))
        stats["total_precision"] += float(metrics.get("precision", 0.0))
        if error:
            stats["errors"] += 1

        if tier not in stats["by_tier"]:
            stats["by_tier"][tier] = {"count": 0, "f1_sum": 0.0, "recall_sum": 0.0}
        stats["by_tier"][tier]["count"] += 1
        stats["by_tier"][tier]["f1_sum"] += float(metrics.get("f1", 0.0))
        stats["by_tier"][tier]["recall_sum"] += float(metrics.get("recall", 0.0))

        if fmt not in stats["by_format"]:
            stats["by_format"][fmt] = {"count": 0, "f1_sum": 0.0, "recall_sum": 0.0}
        stats["by_format"][fmt]["count"] += 1
        stats["by_format"][fmt]["f1_sum"] += float(metrics.get("f1", 0.0))
        stats["by_format"][fmt]["recall_sum"] += float(metrics.get("recall", 0.0))

    for stats in model_stats.values():
        n = stats["total_samples"]
        stats["avg_f1"] = stats["total_f1"] / n if n > 0 else 0.0
        stats["avg_recall"] = stats["total_recall"] / n if n > 0 else 0.0
        stats["avg_precision"] = stats["total_precision"] / n if n > 0 else 0.0

        for tier_stats in stats["by_tier"].values():
            c = tier_stats["count"]
            tier_stats["avg_f1"] = tier_stats["f1_sum"] / c if c > 0 else 0.0
            tier_stats["avg_recall"] = tier_stats["recall_sum"] / c if c > 0 else 0.0

        for fmt_stats in stats["by_format"].values():
            c = fmt_stats["count"]
            fmt_stats["avg_f1"] = fmt_stats["f1_sum"] / c if c > 0 else 0.0
            fmt_stats["avg_recall"] = fmt_stats["recall_sum"] / c if c > 0 else 0.0

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
            "avg_f1",
            "avg_recall",
            "avg_precision",
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

        for group_key in ["by_tier", "by_format"]:
            e_group = e.get(group_key) or {}
            a_group = a.get(group_key) or {}

            if set(e_group.keys()) != set(a_group.keys()):
                errors.append(
                    f"model_stats[{model}].{group_key} keys mismatch (report={sorted(e_group.keys())}, recomputed={sorted(a_group.keys())})"
                )
                continue

            for k, e_stats in e_group.items():
                a_stats = a_group[k]
                for stat_key in ["count", "f1_sum", "recall_sum", "avg_f1", "avg_recall"]:
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
    results_dir = Path(args.results_dir) if args.results_dir else (script_dir / "results")
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

        if entry.get("error"):
            errors.append(f"{sample} / {model}: report has error entry: {entry['error']}")
            continue

        pred_path = results_dir / f"{sample}_{model}_predicted.json"
        if not pred_path.exists():
            errors.append(f"{sample} / {model}: missing predicted file {pred_path}")
            continue

        gt_path = claims_dir / f"{sample}.json"
        if not gt_path.exists():
            errors.append(f"{sample} / {model}: missing ground truth file {gt_path}")
            continue

        predicted_raw = json.loads(pred_path.read_text(encoding="utf-8"))
        try:
            predicted = _validate_and_normalize_predictions(predicted_raw)
        except Exception as e:
            errors.append(f"{sample} / {model}: predicted output failed schema validation: {e}")
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
