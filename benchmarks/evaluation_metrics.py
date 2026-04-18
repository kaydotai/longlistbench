import json
from collections import Counter
from datetime import datetime
from typing import Any

try:
    from .models.loss_run import LossRunIncident
except ImportError:
    from models.loss_run import LossRunIncident


_DATE_FIELDS = {"date_of_loss", "date_reported"}
_OPTIONAL_STR_FIELDS = {
    "cause_code",
    "unit_number",
    "agency",
    "driver_name",
    "adjuster_notes",
}
_BREAKDOWN_KEYS = {"bi", "pd", "lae", "ded"}
_BREAKDOWN_FIELDS = {"reserve", "paid", "recovered", "total_incurred"}


def _normalize_date(value: Any) -> str:
    if value is None:
        return ""
    s = " ".join(str(value).strip().split())
    if not s:
        return ""
    for fmt in (
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m-%d-%Y",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%m/%d/%Y")
        except ValueError:
            continue
    return s


def normalize_incident_number(incident_num: str) -> str:
    if not incident_num:
        return ""
    incident_num = str(incident_num).strip()
    for prefix in ["Incident #", "Incident#", "Incident ", "#", "INC"]:
        if incident_num.startswith(prefix):
            incident_num = incident_num[len(prefix):]
    return incident_num.strip()


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


def _canonicalize_incident(item: dict) -> dict:
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
        elif k in _DATE_FIELDS:
            obj[k] = _normalize_date(v)
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


def evaluate_extraction(predicted: list[dict], ground_truth: list[dict]) -> dict[str, Any]:
    gt_count = len(ground_truth)
    pred_count = len(predicted)

    gt_by_id: dict[str, list[str]] = {}
    pred_by_id: dict[str, list[str]] = {}
    gt_pairs: list[str] = []
    pred_pairs: list[str] = []

    for item in ground_truth:
        obj = _canonicalize_incident(item)
        inc = normalize_incident_number(obj.get("incident_number", ""))
        gt_by_id.setdefault(inc, []).append(json.dumps(obj, sort_keys=True, separators=(",", ":")))
        gt_pairs.extend(_flatten_pairs(inc, obj))

    for item in predicted:
        obj = _canonicalize_incident(item)
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
