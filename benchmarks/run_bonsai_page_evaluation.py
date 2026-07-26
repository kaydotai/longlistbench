#!/usr/bin/env python3
"""Page-wise constrained extraction for Ternary Bonsai endpoints."""

from __future__ import annotations

import argparse
import json
import hashlib
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


DEFAULT_MODEL_KEY = "bonsai_27b_page_pipeline"
DEFAULT_MODEL_ID = "prism-ml/Ternary-Bonsai-27B-mlx-2bit"
DEFAULT_ENDPOINT = "http://127.0.0.1:8080/v1"
DEFAULT_REQUEST_EXTRA_BODY = {
    "chat_template_kwargs": {"enable_thinking": False}
}
_EVENT_WRITE_LOCK = threading.Lock()


@dataclass(frozen=True)
class Page:
    number: int
    text: str


class RetryableInferenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class InferenceResult:
    payload: Any
    attempts: int
    prompt_tokens: int
    completion_tokens: int


class BonsaiClient:
    def __init__(
        self,
        *,
        endpoint: str,
        model_id: str,
        max_attempts: int = 3,
        timeout_seconds: float = 900,
        api_key: str = "local",
        request_extra_body: dict[str, Any] | None = DEFAULT_REQUEST_EXTRA_BODY,
        api: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if api is None:
            from openai import OpenAI

            api = OpenAI(
                base_url=endpoint.rstrip("/") + "/",
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=0,
            )
        self.api = api
        self.endpoint = endpoint.rstrip("/")
        self.model_id = model_id
        self.max_attempts = max_attempts
        self.request_extra_body = request_extra_body
        self.sleep = sleep

    def generate_json(
        self,
        *,
        prompt: str,
        response_format: dict[str, Any],
        max_tokens: int = 8192,
    ) -> InferenceResult:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                request = {
                    "model": self.model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": response_format,
                    "max_tokens": max_tokens,
                }
                if self.request_extra_body is not None:
                    request["extra_body"] = self.request_extra_body
                response = self.api.chat.completions.create(
                    **request,
                )
                if not response.choices:
                    raise RetryableInferenceError("model returned no choices")
                choice = response.choices[0]
                if choice.finish_reason == "length":
                    raise RetryableInferenceError(
                        "generation stopped at the token limit"
                    )
                content = choice.message.content
                if not isinstance(content, str) or not content.strip():
                    raise RetryableInferenceError("model returned no JSON content")
                payload = json.loads(content)
                if not isinstance(payload, dict):
                    raise RetryableInferenceError(
                        "model returned JSON that was not an object"
                    )
                usage = getattr(response, "usage", None)
                return InferenceResult(
                    payload=payload,
                    attempts=attempt,
                    prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                    completion_tokens=int(
                        getattr(usage, "completion_tokens", 0) or 0
                    ),
                )
            except (json.JSONDecodeError, RetryableInferenceError) as exc:
                last_error = (
                    exc
                    if isinstance(exc, RetryableInferenceError)
                    else RetryableInferenceError(f"invalid constrained JSON: {exc}")
                )
            except Exception as exc:
                if not _is_retryable_transport_error(exc):
                    raise
                last_error = RetryableInferenceError(str(exc))

            if attempt < self.max_attempts:
                self.sleep(float(2 ** (attempt - 1)))

        assert last_error is not None
        raise last_error

def _is_retryable_transport_error(exc: Exception) -> bool:
    try:
        from openai import (
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
            RateLimitError,
        )
    except ImportError:
        return False
    return isinstance(
        exc,
        (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError),
    )


@dataclass(frozen=True)
class PublicContract:
    template: str
    output_key: str
    fields_by_type: dict[str, dict[str, dict[str, Any]]]
    required_fields: dict[str, tuple[str, ...]]
    identity_fields: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class CandidateFragment:
    page_number: int
    record: dict[str, Any]


@dataclass(frozen=True)
class CandidateGroup:
    record_type: str
    identity: tuple[Any, ...]
    pages: tuple[int, ...]
    fragments: tuple[CandidateFragment, ...]
    merged: dict[str, Any]
    conflicts: tuple[str, ...]


_STRING = {"type": "string"}
_INTEGER = {"type": "integer"}
_NUMBER = {"type": "number"}
_NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_NULLABLE_NUMBER = {"anyOf": [{"type": "number"}, {"type": "null"}]}


def _field_map(
    names: str,
    *,
    integers: str = "",
    numbers: str = "",
    nullable_strings: str = "",
    nullable_numbers: str = "",
    special: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    fields = {name: dict(_STRING) for name in names.split() if name}
    for name in integers.split():
        fields[name] = dict(_INTEGER)
    for name in numbers.split():
        fields[name] = dict(_NUMBER)
    for name in nullable_strings.split():
        fields[name] = {
            "anyOf": [{"type": "string"}, {"type": "null"}],
        }
    for name in nullable_numbers.split():
        fields[name] = {
            "anyOf": [{"type": "number"}, {"type": "null"}],
        }
    fields.update(special or {})
    return fields


_FINANCIAL = {
    "type": "object",
    "properties": {
        "reserve": dict(_NUMBER),
        "paid": dict(_NUMBER),
        "recovered": dict(_NUMBER),
        "total_incurred": dict(_NUMBER),
    },
    "required": ["reserve", "paid", "recovered", "total_incurred"],
    "additionalProperties": False,
}

_CONTRACT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "driver_mvr_request_and_roster": {
        "output_key": "records",
        "types": {
            "record": _field_map(
                "date_hired date_of_birth license_class license_number mvr_run_date "
                "name state_licensed years_experienced accidents_last_5_years mvr_violations",
                integers="years_experienced",
                nullable_strings="accidents_last_5_years mvr_violations",
            )
        },
        "identity": {"record": ("license_number",)},
    },
    "driver_schedule_spreadsheet_export": {
        "output_key": "records",
        "types": {
            "record": _field_map(
                "date_of_birth driver_license_number name state_licensed"
            )
        },
        "identity": {"record": ("driver_license_number",)},
    },
    "ifta_mileage_by_vehicle": {
        "output_key": "records",
        "types": {
            "record": _field_map(
                "state vehicle identified_miles total_miles unidentified_miles",
                numbers="identified_miles total_miles unidentified_miles",
            )
        },
        "identity": {"record": ("vehicle", "state")},
    },
    "ifta_multisection_return_packet": {
        "output_key": "records",
        "types": {
            "record": _field_map(
                "filing_type fuel_type jurisdiction quarter return_id filing_year "
                "interest_due net_gallons surtax_due tax_due_refund tax_paid_gallons "
                "tax_rate taxable_gallons taxable_miles total_due_refund total_miles",
                integers=(
                    "filing_year net_gallons tax_paid_gallons taxable_gallons "
                    "taxable_miles total_miles"
                ),
                numbers="interest_due surtax_due tax_due_refund tax_rate total_due_refund",
            )
        },
        "identity": {"record": ("return_id", "jurisdiction", "fuel_type")},
    },
    "ifta_return_schedule_details": {
        "output_key": "records",
        "types": {
            "record": _field_map(
                "jurisdiction schedule surcharge distance_miles interest_due "
                "net_taxable_volume tax_due_credit tax_paid_volume tax_rate "
                "taxable_distance_miles taxable_volume total_due",
                integers=(
                    "distance_miles net_taxable_volume tax_paid_volume "
                    "taxable_distance_miles taxable_volume"
                ),
                nullable_numbers="interest_due tax_due_credit tax_rate total_due",
            )
        },
        "identity": {"record": ("schedule", "jurisdiction")},
    },
    "ifta_tax_return_inquiry_detail": {
        "output_key": "records",
        "types": {
            "record": _field_map(
                "field section value page",
                integers="page",
            )
        },
        "identity": {"record": ("page", "section", "field")},
    },
    "ifta_tax_return_summary": {
        "output_key": "records",
        "types": {
            "record": _field_map(
                "fuel_type jurisdiction gallons_purchased interest_due "
                "net_taxable_gallons surtax_due tax_due_refund tax_rate "
                "taxable_gallons taxable_miles total_due_refund total_miles",
                integers=(
                    "gallons_purchased net_taxable_gallons taxable_gallons "
                    "taxable_miles total_miles"
                ),
                numbers="interest_due surtax_due tax_due_refund tax_rate total_due_refund",
            )
        },
        "identity": {"record": ("jurisdiction", "fuel_type")},
    },
    "loss_run_external": {
        "output_key": "records",
        "types": {
            "record": _field_map(
                "adjuster claim_number claim_reported claim_status claimant date_closed "
                "date_of_loss date_reported description driver effective_date policy_number "
                "claim_paid claim_recovered claim_reserves",
                numbers="claim_paid claim_recovered claim_reserves",
            )
        },
        "identity": {"record": ("claim_number",)},
    },
    "claim_crosspage_multihop": {
        "output_key": "incidents",
        "types": {
            "record": _field_map(
                "incident_number reference_number company_name division coverage_type "
                "status policy_number policy_state cause_code description handler "
                "unit_number date_of_loss loss_state date_reported agency insured "
                "driver_name adjuster_notes",
                nullable_strings="cause_code unit_number agency driver_name adjuster_notes",
                special={
                    "claimants": {"type": "array", "items": dict(_STRING)},
                    "bi": _FINANCIAL,
                    "pd": _FINANCIAL,
                    "lae": _FINANCIAL,
                    "ded": _FINANCIAL,
                },
            )
        },
        "identity": {"record": ("incident_number",)},
    },
    "vehicle_schedule_spreadsheet_export": {
        "output_key": "records",
        "types": {
            "record": _field_map(
                "body_type company_vehicle_number make model plate_number veh_number year",
                integers="year",
            )
        },
        "identity": {"record": ("veh_number",)},
    },
}


def _policy_types(definitions: dict[str, str]) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        record_type: _field_map(f"record_type {fields}")
        for record_type, fields in definitions.items()
    }


_CONTRACT_DEFINITIONS.update(
    {
        "policy_multihop_bop": {
            "output_key": "records",
            "types": _policy_types(
                {
                    "bop_coverage_item": (
                        "building_number business_income_basis class_code classification "
                        "coinsurance coverage deductible edition_date form_number form_title "
                        "limit lob location_number named_insured policy_number policy_period "
                        "premises_address premium valuation"
                    ),
                    "policy_location_item": (
                        "building_number class_code classification lob location_number "
                        "named_insured policy_number policy_period premises_address"
                    ),
                    "policy_form_item": (
                        "edition_date form_number form_title lob named_insured policy_number "
                        "policy_period schedule_source"
                    ),
                    "policy_endorsement_item": (
                        "building_number coverage deductible edition_date "
                        "endorsement_effective_date form_number form_title limit lob "
                        "location_number named_insured policy_number policy_period"
                    ),
                    "policy_premium_item": (
                        "building_number class_code coverage limit lob location_number "
                        "named_insured policy_number policy_period premium premium_basis"
                    ),
                    "policy_clause_item": (
                        "building_number clause_scope clause_text clause_title clause_type "
                        "coverage deductible edition_date form_number form_title limit lob "
                        "location_number named_insured policy_number policy_period"
                    ),
                }
            ),
            "identity": {
                "bop_coverage_item": (
                    "policy_number",
                    "location_number",
                    "building_number",
                    "class_code",
                    "coverage",
                ),
                "policy_location_item": (
                    "policy_number",
                    "location_number",
                    "building_number",
                    "class_code",
                ),
                "policy_form_item": ("policy_number", "form_number", "edition_date"),
                "policy_endorsement_item": (
                    "policy_number",
                    "form_number",
                    "endorsement_effective_date",
                    "location_number",
                    "building_number",
                ),
                "policy_premium_item": (
                    "policy_number",
                    "location_number",
                    "building_number",
                    "class_code",
                    "coverage",
                    "premium_basis",
                ),
                "policy_clause_item": (
                    "policy_number",
                    "form_number",
                    "clause_scope",
                    "clause_type",
                    "clause_title",
                ),
            },
        },
        "policy_multihop_wc": {
            "output_key": "records",
            "types": _policy_types(
                {
                    "wc_class_code_item": (
                        "annual_payroll class_code classification edition_date "
                        "endorsement_effective_date estimated_premium experience_mod "
                        "form_number form_title governing_class lob location_number "
                        "manual_rate named_insured policy_number policy_period premium_basis "
                        "schedule_credit_debit state"
                    ),
                    "policy_location_item": (
                        "class_code classification governing_class lob location_number "
                        "named_insured policy_number policy_period state"
                    ),
                    "policy_form_item": (
                        "edition_date form_number form_title lob named_insured policy_number "
                        "policy_period schedule_source"
                    ),
                    "policy_endorsement_item": (
                        "annual_payroll class_code classification edition_date "
                        "endorsement_effective_date estimated_premium form_number form_title "
                        "lob materiality named_insured policy_number policy_period state"
                    ),
                    "policy_premium_item": (
                        "annual_payroll class_code experience_mod lob location_number "
                        "manual_rate named_insured policy_number policy_period premium "
                        "premium_basis schedule_credit_debit state"
                    ),
                    "policy_clause_item": (
                        "annual_payroll class_code classification clause_scope clause_text "
                        "clause_title clause_type edition_date estimated_premium form_number "
                        "form_title lob named_insured policy_number policy_period state"
                    ),
                }
            ),
            "identity": {
                "wc_class_code_item": (
                    "policy_number",
                    "state",
                    "class_code",
                    "location_number",
                ),
                "policy_location_item": (
                    "policy_number",
                    "state",
                    "location_number",
                    "class_code",
                ),
                "policy_form_item": ("policy_number", "form_number", "edition_date"),
                "policy_endorsement_item": (
                    "policy_number",
                    "form_number",
                    "endorsement_effective_date",
                    "state",
                    "class_code",
                ),
                "policy_premium_item": (
                    "policy_number",
                    "state",
                    "location_number",
                    "class_code",
                    "premium_basis",
                ),
                "policy_clause_item": (
                    "policy_number",
                    "form_number",
                    "clause_scope",
                    "clause_type",
                    "clause_title",
                ),
            },
        },
        "policy_multihop_cgl": {
            "output_key": "records",
            "types": _policy_types(
                {
                    "cgl_exposure_item": (
                        "class_code classification coverage_part edition_date "
                        "endorsement_effective_date exclusion_name exposure exposure_basis "
                        "form_number form_title limit limit_type lob location_number "
                        "named_insured policy_number policy_period premium "
                        "products_completed_ops_rate rate territory"
                    ),
                    "policy_location_item": (
                        "class_code classification exposure_basis lob location_number "
                        "named_insured policy_number policy_period territory"
                    ),
                    "policy_form_item": (
                        "edition_date exclusion_name form_number form_title lob named_insured "
                        "policy_number policy_period schedule_source"
                    ),
                    "policy_endorsement_item": (
                        "class_code classification edition_date endorsement_effective_date "
                        "exclusion_name form_number form_title limit limit_type lob "
                        "location_number materiality named_insured policy_number policy_period"
                    ),
                    "policy_premium_item": (
                        "class_code exposure lob location_number named_insured policy_number "
                        "policy_period premium premium_basis products_completed_ops_rate rate"
                    ),
                    "policy_clause_item": (
                        "class_code classification clause_scope clause_text clause_title "
                        "clause_type edition_date exclusion_name form_number form_title limit "
                        "limit_type lob location_number named_insured policy_number "
                        "policy_period territory"
                    ),
                }
            ),
            "identity": {
                "cgl_exposure_item": (
                    "policy_number",
                    "location_number",
                    "class_code",
                    "coverage_part",
                ),
                "policy_location_item": (
                    "policy_number",
                    "location_number",
                    "class_code",
                ),
                "policy_form_item": ("policy_number", "form_number", "edition_date"),
                "policy_endorsement_item": (
                    "policy_number",
                    "form_number",
                    "endorsement_effective_date",
                    "location_number",
                    "class_code",
                ),
                "policy_premium_item": (
                    "policy_number",
                    "location_number",
                    "class_code",
                    "premium_basis",
                ),
                "policy_clause_item": (
                    "policy_number",
                    "form_number",
                    "clause_scope",
                    "clause_type",
                    "clause_title",
                ),
            },
        },
    }
)


def contract_for_template(template: str) -> PublicContract:
    try:
        definition = _CONTRACT_DEFINITIONS[template]
    except KeyError as exc:
        raise ValueError(f"Unsupported template: {template}") from exc
    fields_by_type = definition["types"]
    return PublicContract(
        template=template,
        output_key=definition["output_key"],
        fields_by_type=fields_by_type,
        required_fields={
            record_type: tuple(fields)
            for record_type, fields in fields_by_type.items()
        },
        identity_fields=definition["identity"],
    )


def _page_fields(
    contract: PublicContract,
    record_type: str,
) -> tuple[str, ...]:
    return tuple(
        field
        for field in contract.required_fields[record_type]
        if field != "record_type"
    )


def _nullable_page_schema(schema: dict[str, Any]) -> dict[str, Any]:
    choices = list(schema.get("anyOf", [schema]))
    if not any(choice == {"type": "null"} for choice in choices):
        choices.append({"type": "null"})
    return {"anyOf": choices}


def _page_row_schema(
    contract: PublicContract,
    record_type: str,
) -> dict[str, Any]:
    fields = _page_fields(contract, record_type)
    return {
        "type": "array",
        "prefixItems": [
            _nullable_page_schema(contract.fields_by_type[record_type][field])
            for field in fields
        ],
        "minItems": len(fields),
        "maxItems": len(fields),
    }


def page_response_format(contract: PublicContract) -> dict[str, Any]:
    record_types = tuple(contract.required_fields)
    if len(record_types) == 1:
        properties = {
            "rows": {
                "type": "array",
                "items": _page_row_schema(contract, record_types[0]),
            }
        }
        required = ["rows"]
    else:
        properties = {
            record_type: {
                "type": "array",
                "items": _page_row_schema(contract, record_type),
            }
            for record_type in sorted(record_types)
        }
        required = sorted(record_types)
    schema = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "page_extraction",
            "strict": True,
            "schema": schema,
        },
    }


def _schema_allows_null(schema: dict[str, Any]) -> bool:
    return any(
        choice == {"type": "null"}
        for choice in schema.get("anyOf", [])
    )


def build_page_prompt(contract: PublicContract, page: Page) -> str:
    groups = "\n".join(
        f"- {('rows' if len(contract.required_fields) == 1 else record_type)}: "
        f"[{', '.join(_page_fields(contract, record_type))}]"
        for record_type in contract.required_fields
    )
    return f"""Extract target record evidence from exactly one OCR page.

Return every target row visible on the page. Also return partial rows when this
page contains fields whose other fields may be on another page. Each output row
is a compact array in the exact column order below. Use null for a field that is
not visible. Never use an empty string, zero, an empty array, or an empty object
as a placeholder. Return an empty array for a group absent from the page. Never
guess. Ignore summaries, totals, instructions, and unrelated tables.

Output groups and exact row column order:
{groups}

Return only the schema-constrained JSON object, minified on one line.

OCR page:
{page.text}"""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _request_fingerprint(
    *,
    client: Any,
    prompt: str,
    response_format: dict[str, Any],
) -> str:
    payload = {
        "model_id": getattr(client, "model_id", None),
        "endpoint": getattr(client, "endpoint", None),
        "request_extra_body": getattr(client, "request_extra_body", None),
        "prompt": prompt,
        "response_format": response_format,
    }
    return _sha256_text(
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


def build_page_checkpoint(
    *,
    sample: str,
    page: Page,
    candidates: list[dict[str, Any]],
    attempts: int,
    prompt_tokens: int,
    completion_tokens: int,
    request_fingerprint: str | None = None,
    model_id: str | None = None,
    endpoint: str | None = None,
) -> dict[str, Any]:
    return {
        "sample": sample,
        "page_number": page.number,
        "page_sha256": _sha256_text(page.text),
        "request_fingerprint": request_fingerprint,
        "model_id": model_id,
        "endpoint": endpoint,
        "candidates": candidates,
        "attempts": attempts,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def append_event(output_dir: Path, event: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    with _EVENT_WRITE_LOCK:
        with (output_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def _valid_page_checkpoint(
    payload: Any,
    *,
    sample: str,
    page: Page,
    request_fingerprint: str,
) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("sample") == sample
        and payload.get("page_number") == page.number
        and payload.get("page_sha256") == _sha256_text(page.text)
        and payload.get("request_fingerprint") == request_fingerprint
        and isinstance(payload.get("candidates"), list)
    )


def _validate_candidates(
    payload: dict[str, Any],
    contract: PublicContract,
) -> list[dict[str, Any]]:
    if "candidates" not in payload:
        return _decode_compact_page_rows(payload, contract)

    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise RetryableInferenceError("page output did not contain a candidates list")
    allowed = {
        field
        for fields in contract.fields_by_type.values()
        for field in fields
    }
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise RetryableInferenceError(
                f"candidate {index} was not a JSON object"
            )
        extra = set(candidate) - allowed
        if extra:
            raise RetryableInferenceError(
                f"candidate {index} had unsupported fields: {sorted(extra)}"
            )
        if len(contract.required_fields) > 1:
            if candidate.get("record_type") not in contract.required_fields:
                raise RetryableInferenceError(
                    f"candidate {index} had an unsupported record_type"
                )
    return candidates


def _decode_compact_page_rows(
    payload: dict[str, Any],
    contract: PublicContract,
) -> list[dict[str, Any]]:
    record_types = tuple(contract.required_fields)
    group_names = (
        {"rows": record_types[0]}
        if len(record_types) == 1
        else {record_type: record_type for record_type in record_types}
    )
    if set(payload) != set(group_names):
        raise RetryableInferenceError(
            "page output did not contain exactly the expected row groups"
        )

    candidates: list[dict[str, Any]] = []
    for group_name, record_type in group_names.items():
        rows = payload[group_name]
        if not isinstance(rows, list):
            raise RetryableInferenceError(
                f"page row group {group_name!r} was not a list"
            )
        fields = _page_fields(contract, record_type)
        for index, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != len(fields):
                raise RetryableInferenceError(
                    f"{group_name} row {index} did not have {len(fields)} values"
                )
            candidate = {
                field: value
                for field, value in zip(fields, row, strict=True)
                if value is not None
            }
            if len(record_types) > 1:
                candidate["record_type"] = record_type
            candidates.append(candidate)
    return candidates


def _generate_validated_json(
    *,
    client: BonsaiClient,
    prompt: str,
    response_format: dict[str, Any],
    validator: Callable[[dict[str, Any]], Any],
    validation_attempts: int,
    sleep: Callable[[float], None],
    on_retry: Callable[[RetryableInferenceError, int], None],
) -> tuple[InferenceResult, Any]:
    total_attempts = 0
    last_error: RetryableInferenceError | None = None
    for validation_attempt in range(1, validation_attempts + 1):
        inference = client.generate_json(
            prompt=prompt,
            response_format=response_format,
        )
        total_attempts += inference.attempts
        try:
            value = validator(inference.payload)
            return (
                InferenceResult(
                    payload=inference.payload,
                    attempts=total_attempts,
                    prompt_tokens=inference.prompt_tokens,
                    completion_tokens=inference.completion_tokens,
                ),
                value,
            )
        except RetryableInferenceError as exc:
            last_error = exc
            if validation_attempt >= validation_attempts:
                break
            on_retry(exc, validation_attempt)
            sleep(float(2 ** (validation_attempt - 1)))
    assert last_error is not None
    raise last_error


def extract_pages(
    *,
    sample: str,
    pages: list[Page],
    contract: PublicContract,
    client: BonsaiClient,
    output_dir: Path,
    resume: bool,
    validation_attempts: int = 3,
    page_workers: int = 1,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    if page_workers < 1:
        raise ValueError("page_workers must be at least 1")
    page_dir = output_dir / "pages" / sample
    results: dict[int, dict[str, Any]] = {}
    pending: list[Page] = []
    for page in pages:
        checkpoint_path = page_dir / f"page_{page.number:04d}.json"
        request_fingerprint = _request_fingerprint(
            client=client,
            prompt=build_page_prompt(contract, page),
            response_format=page_response_format(contract),
        )
        if resume and checkpoint_path.is_file():
            try:
                checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                checkpoint = None
            if _valid_page_checkpoint(
                checkpoint,
                sample=sample,
                page=page,
                request_fingerprint=request_fingerprint,
            ):
                results[page.number] = checkpoint
                continue
        pending.append(page)

    def extract_one(page: Page) -> dict[str, Any]:
        checkpoint_path = page_dir / f"page_{page.number:04d}.json"
        started = time.monotonic()
        prompt = build_page_prompt(contract, page)
        response_format = page_response_format(contract)
        request_fingerprint = _request_fingerprint(
            client=client,
            prompt=prompt,
            response_format=response_format,
        )
        inference, candidates = _generate_validated_json(
            client=client,
            prompt=prompt,
            response_format=response_format,
            validator=lambda payload: _validate_candidates(payload, contract),
            validation_attempts=validation_attempts,
            sleep=sleep,
            on_retry=lambda exc, attempt: append_event(
                output_dir,
                {
                    "type": "inference_retry",
                    "stage": "page",
                    "sample": sample,
                    "page_number": page.number,
                    "attempt": attempt,
                    "error": str(exc),
                },
            ),
        )
        checkpoint = build_page_checkpoint(
            sample=sample,
            page=page,
            candidates=candidates,
            attempts=inference.attempts,
            prompt_tokens=inference.prompt_tokens,
            completion_tokens=inference.completion_tokens,
            request_fingerprint=request_fingerprint,
            model_id=getattr(client, "model_id", None),
            endpoint=getattr(client, "endpoint", None),
        )
        checkpoint["elapsed_seconds"] = time.monotonic() - started
        _atomic_write_json(checkpoint_path, checkpoint)
        append_event(
            output_dir,
            {
                "type": "page_complete",
                "sample": sample,
                "page_number": page.number,
                "candidate_count": len(candidates),
                "attempts": inference.attempts,
                "checkpoint": checkpoint_path.relative_to(output_dir).as_posix(),
            },
        )
        return checkpoint

    if page_workers == 1:
        for page in pending:
            results[page.number] = extract_one(page)
    else:
        with ThreadPoolExecutor(
            max_workers=page_workers,
            thread_name_prefix="bonsai-page",
        ) as executor:
            future_pages = {
                executor.submit(extract_one, page): page
                for page in pending
            }
            for future in as_completed(future_pages):
                page = future_pages[future]
                results[page.number] = future.result()

    return [results[page.number] for page in pages]


def _candidate_record_type(
    candidate: dict[str, Any],
    contract: PublicContract,
) -> str:
    if len(contract.required_fields) == 1:
        return next(iter(contract.required_fields))
    record_type = candidate.get("record_type")
    if record_type not in contract.required_fields:
        raise ValueError(f"Unsupported record_type: {record_type!r}")
    return str(record_type)


def _identity_for_candidate(
    candidate: dict[str, Any],
    *,
    record_type: str,
    contract: PublicContract,
) -> tuple[Any, ...] | None:
    values: list[Any] = []
    for field in contract.identity_fields[record_type]:
        value = candidate.get(field)
        if value is None or value == "":
            return None
        values.append(value)
    return tuple(values)


def _is_blank(value: Any) -> bool:
    return value is None or value == "" or value == []


def _merge_values(left: Any, right: Any) -> tuple[Any, bool]:
    if left == right:
        return left, False
    if _is_blank(left):
        return right, False
    if _is_blank(right):
        return left, False
    if isinstance(left, list) and isinstance(right, list):
        merged = list(left)
        for item in right:
            if item not in merged:
                merged.append(item)
        return merged, False
    if isinstance(left, dict) and isinstance(right, dict):
        merged = dict(left)
        conflict = False
        for key, value in right.items():
            if key not in merged:
                merged[key] = value
                continue
            merged[key], field_conflict = _merge_values(merged[key], value)
            conflict = conflict or field_conflict
        return merged, conflict
    return left, True


def _build_candidate_group(
    *,
    record_type: str,
    identity: tuple[Any, ...],
    fragments: list[CandidateFragment],
) -> CandidateGroup:
    merged: dict[str, Any] = {}
    conflicts: set[str] = set()
    unique_fragments: list[CandidateFragment] = []
    seen: set[str] = set()
    for fragment in fragments:
        fingerprint = json.dumps(
            fragment.record,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique_fragments.append(fragment)
        for field, value in fragment.record.items():
            if field not in merged:
                merged[field] = value
                continue
            merged[field], field_conflict = _merge_values(merged[field], value)
            if field_conflict:
                conflicts.add(field)
    return CandidateGroup(
        record_type=record_type,
        identity=identity,
        pages=tuple(dict.fromkeys(item.page_number for item in unique_fragments)),
        fragments=tuple(unique_fragments),
        merged=merged,
        conflicts=tuple(sorted(conflicts)),
    )


def _group_is_complete(group: CandidateGroup, contract: PublicContract) -> bool:
    return all(
        field in group.merged
        for field in contract.required_fields[group.record_type]
    )


def _fill_nullable_defaults(
    group: CandidateGroup,
    contract: PublicContract,
) -> CandidateGroup:
    merged = dict(group.merged)
    for field, schema in contract.fields_by_type[group.record_type].items():
        if _schema_allows_null(schema) and (
            field not in merged or _is_blank(merged[field])
        ):
            merged[field] = None
    return CandidateGroup(
        record_type=group.record_type,
        identity=group.identity,
        pages=group.pages,
        fragments=group.fragments,
        merged=merged,
        conflicts=group.conflicts,
    )


def collapse_and_reconcile(
    *,
    page_results: list[dict[str, Any]],
    contract: PublicContract,
    reduce_group: Callable[[CandidateGroup], dict[str, Any]],
    reduction_workers: int = 1,
) -> list[dict[str, Any]]:
    if reduction_workers < 1:
        raise ValueError("reduction_workers must be at least 1")
    grouped: dict[tuple[Any, ...], list[CandidateFragment]] = {}
    group_types: dict[tuple[Any, ...], str] = {}
    for page_result in page_results:
        page_number = int(page_result["page_number"])
        for candidate in page_result["candidates"]:
            record = dict(candidate)
            record_type = _candidate_record_type(record, contract)
            identity = _identity_for_candidate(
                record,
                record_type=record_type,
                contract=contract,
            )
            if identity is None:
                continue
            group_key = (record_type, *identity)
            grouped.setdefault(group_key, []).append(
                CandidateFragment(page_number=page_number, record=record)
            )
            group_types[group_key] = record_type

    records: list[dict[str, Any] | None] = [None] * len(grouped)
    pending: list[tuple[int, CandidateGroup]] = []
    for index, (group_key, fragments) in enumerate(grouped.items()):
        group = _build_candidate_group(
            record_type=group_types[group_key],
            identity=group_key,
            fragments=fragments,
        )
        group = _fill_nullable_defaults(group, contract)
        if not group.conflicts and _group_is_complete(group, contract):
            records[index] = group.merged
        else:
            pending.append((index, group))

    if reduction_workers == 1:
        for index, group in pending:
            records[index] = reduce_group(group)
    else:
        with ThreadPoolExecutor(max_workers=reduction_workers) as executor:
            future_to_index = {
                executor.submit(reduce_group, group): index
                for index, group in pending
            }
            for future in as_completed(future_to_index):
                records[future_to_index[future]] = future.result()

    assert all(record is not None for record in records)
    return [record for record in records if record is not None]


def final_response_format(
    contract: PublicContract,
    record_type: str,
) -> dict[str, Any]:
    properties = {
        name: schema
        for name, schema in contract.fields_by_type[record_type].items()
    }
    if len(contract.required_fields) > 1:
        properties["record_type"] = {
            "type": "string",
            "enum": [record_type],
        }
    record_schema = {
        "type": "object",
        "properties": properties,
        "required": list(contract.required_fields[record_type]),
        "additionalProperties": False,
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "consolidated_record",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"record": record_schema},
                "required": ["record"],
                "additionalProperties": False,
            },
        },
    }


def _reduction_fingerprint(
    group: CandidateGroup,
    pages_by_number: dict[int, Page],
    contract: PublicContract,
    client: Any,
) -> str:
    return _request_fingerprint(
        client=client,
        prompt=build_reduction_prompt(
            group=group,
            contract=contract,
            pages_by_number=pages_by_number,
        ),
        response_format=final_response_format(contract, group.record_type),
    )


def build_reduction_prompt(
    *,
    group: CandidateGroup,
    contract: PublicContract,
    pages_by_number: dict[int, Page],
) -> str:
    required = ", ".join(contract.required_fields[group.record_type])
    record_schema = final_response_format(
        contract,
        group.record_type,
    )["json_schema"]["schema"]["properties"]["record"]
    schema = json.dumps(record_schema, indent=2, ensure_ascii=False)
    fragments = json.dumps(
        [
            {
                "page_number": fragment.page_number,
                "record": fragment.record,
            }
            for fragment in group.fragments
        ],
        indent=2,
        ensure_ascii=False,
    )
    return f"""Consolidate evidence for exactly one logical {group.record_type} record.

Use only the candidate fragments below. They were extracted independently from
single source pages. Resolve repeated or conflicting values from those
fragments. Return one record with every required field. Use an empty string,
null, empty list, or zero only when the fragments do not provide a value. Do
not create a different logical record.

Required fields:
{required}

Expected record JSON Schema:
{schema}

Candidate fragments:
{fragments}
"""


def _validate_final_record(
    payload: dict[str, Any],
    contract: PublicContract,
    record_type: str,
) -> dict[str, Any]:
    record = payload.get("record")
    if not isinstance(record, dict):
        raise RetryableInferenceError("reducer output did not contain one record")
    allowed = set(contract.fields_by_type[record_type])
    extra = set(record) - allowed
    if extra:
        raise RetryableInferenceError(
            f"reducer record had unsupported fields: {sorted(extra)}"
        )
    missing = set(contract.required_fields[record_type]) - set(record)
    if missing:
        raise RetryableInferenceError(
            f"reducer record missed required fields: {sorted(missing)}"
        )
    if len(contract.required_fields) > 1 and record.get("record_type") != record_type:
        raise RetryableInferenceError("reducer changed the record_type")
    return record


def reduce_candidate_group(
    *,
    sample: str,
    group: CandidateGroup,
    contract: PublicContract,
    pages_by_number: dict[int, Page],
    client: BonsaiClient,
    output_dir: Path,
    resume: bool,
    validation_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    prompt = build_reduction_prompt(
        group=group,
        contract=contract,
        pages_by_number=pages_by_number,
    )
    response_format = final_response_format(contract, group.record_type)
    fingerprint = _reduction_fingerprint(
        group,
        pages_by_number,
        contract,
        client,
    )
    checkpoint_path = (
        output_dir / "reductions" / sample / f"{fingerprint[:24]}.json"
    )
    if resume and checkpoint_path.is_file():
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            checkpoint = None
        if (
            isinstance(checkpoint, dict)
            and checkpoint.get("fingerprint") == fingerprint
            and isinstance(checkpoint.get("record"), dict)
        ):
            return _validate_final_record(
                {"record": checkpoint["record"]},
                contract,
                group.record_type,
            )

    started = time.monotonic()
    inference, record = _generate_validated_json(
        client=client,
        prompt=prompt,
        response_format=response_format,
        validator=lambda payload: _validate_final_record(
            payload,
            contract,
            group.record_type,
        ),
        validation_attempts=validation_attempts,
        sleep=sleep,
        on_retry=lambda exc, attempt: append_event(
            output_dir,
            {
                "type": "inference_retry",
                "stage": "reduce",
                "sample": sample,
                "record_type": group.record_type,
                "identity": list(group.identity),
                "attempt": attempt,
                "error": str(exc),
            },
        ),
    )
    checkpoint = {
        "sample": sample,
        "fingerprint": fingerprint,
        "model_id": getattr(client, "model_id", None),
        "endpoint": getattr(client, "endpoint", None),
        "record_type": group.record_type,
        "identity": list(group.identity),
        "pages": list(group.pages),
        "attempts": inference.attempts,
        "prompt_tokens": inference.prompt_tokens,
        "completion_tokens": inference.completion_tokens,
        "elapsed_seconds": time.monotonic() - started,
        "record": record,
    }
    _atomic_write_json(checkpoint_path, checkpoint)
    append_event(
        output_dir,
        {
            "type": "reduction_complete",
            "sample": sample,
            "record_type": group.record_type,
            "identity": list(group.identity),
            "pages": list(group.pages),
            "attempts": inference.attempts,
            "checkpoint": checkpoint_path.relative_to(output_dir).as_posix(),
        },
    )
    return record


def _transcript_file(dataset_dir: Path, sample: str, transcript: str) -> Path:
    if transcript == "ocr":
        return dataset_dir / "transcripts" / "ocr_gemini" / f"{sample}.md"
    if transcript == "canonical":
        return dataset_dir / "transcripts" / "canonical" / f"{sample}.md"
    raise ValueError(f"Unsupported transcript condition: {transcript}")


def run_document(
    *,
    dataset_dir: Path,
    sample: str,
    transcript: str,
    output_dir: Path,
    model_key: str,
    client: BonsaiClient,
    resume: bool,
    validation_attempts: int = 3,
    page_workers: int = 1,
    reduction_workers: int = 1,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    started = time.monotonic()
    metadata_path = dataset_dir / "metadata" / f"{sample}.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    template = metadata.get("template") or metadata.get("complexity_regime")
    contract = contract_for_template(str(template))
    transcript_text = _transcript_file(
        dataset_dir,
        sample,
        transcript,
    ).read_text(encoding="utf-8")
    pages = split_ocr_pages(transcript_text)
    pages_by_number = {page.number: page for page in pages}

    page_results = extract_pages(
        sample=sample,
        pages=pages,
        contract=contract,
        client=client,
        output_dir=output_dir,
        resume=resume,
        validation_attempts=validation_attempts,
        page_workers=page_workers,
        sleep=sleep,
    )

    def reduce_one(group: CandidateGroup) -> dict[str, Any]:
        return reduce_candidate_group(
            sample=sample,
            group=group,
            contract=contract,
            pages_by_number=pages_by_number,
            client=client,
            output_dir=output_dir,
            resume=resume,
            validation_attempts=validation_attempts,
            sleep=sleep,
        )

    records = collapse_and_reconcile(
        page_results=page_results,
        contract=contract,
        reduce_group=reduce_one,
        reduction_workers=reduction_workers,
    )
    if contract.output_key == "incidents":
        try:
            from .extraction_core import _validate_and_normalize_predictions
        except ImportError:
            from extraction_core import _validate_and_normalize_predictions

        records = _validate_and_normalize_predictions({"incidents": records})
    else:
        try:
            from .evaluation_metrics import normalize_record_predictions
        except ImportError:
            from evaluation_metrics import normalize_record_predictions

        records = normalize_record_predictions(records)

    prediction_path = (
        output_dir / f"{sample}_{transcript}_{model_key}_predicted.json"
    )
    _atomic_write_json(prediction_path, records)
    reduction_dir = output_dir / "reductions" / sample
    reduction_checkpoints: list[dict[str, Any]] = []
    if reduction_dir.is_dir():
        for path in reduction_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                reduction_checkpoints.append(payload)
    reductions = len(reduction_checkpoints)
    result = {
        "sample": sample,
        "template": template,
        "transcript": transcript,
        "page_count": len(pages),
        "predicted_count": len(records),
        "reduction_count": reductions,
        "prompt_tokens": (
            sum(int(item.get("prompt_tokens", 0)) for item in page_results)
            + sum(
                int(item.get("prompt_tokens", 0))
                for item in reduction_checkpoints
            )
        ),
        "completion_tokens": sum(
            int(item.get("completion_tokens", 0)) for item in page_results
        )
        + sum(
            int(item.get("completion_tokens", 0))
            for item in reduction_checkpoints
        ),
        "extraction_time": time.monotonic() - started,
        "prediction_file": prediction_path.name,
        "prediction_sha256": hashlib.sha256(prediction_path.read_bytes()).hexdigest(),
        "transcript_sha256": _sha256_text(transcript_text),
    }
    append_event(
        output_dir,
        {
            "type": "document_complete",
            "sample": sample,
            "page_count": len(pages),
            "predicted_count": len(records),
            "reduction_count": reductions,
            "prediction_file": prediction_path.name,
        },
    )
    return result


def discover_samples(
    dataset_dir: Path,
    requested: list[str] | None,
) -> list[str]:
    if requested:
        return list(requested)
    manifest = json.loads(
        (dataset_dir / "manifest.json").read_text(encoding="utf-8")
    )
    return sorted(str(instance["id"]) for instance in manifest["instances"])


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run page-wise constrained extraction and per-record reconciliation "
            "against an OpenAI-compatible Ternary Bonsai 27B endpoint"
        )
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--dataset-dir", default="data")
    parser.add_argument("--transcript", default="ocr", choices=["ocr", "canonical"])
    parser.add_argument("--samples", nargs="+", default=None)
    parser.add_argument("--model-key", default=DEFAULT_MODEL_KEY)
    parser.add_argument("--model", default=DEFAULT_MODEL_ID)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument(
        "--api-key-env",
        default=None,
        help="Name of an environment variable containing the API key",
    )
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--validation-attempts", type=int, default=3)
    parser.add_argument("--document-attempts", type=int, default=2)
    parser.add_argument(
        "--page-workers",
        type=int,
        default=1,
        help=(
            "Independent one-page requests to run concurrently; pages are "
            "never combined into one context"
        ),
    )
    parser.add_argument(
        "--reduction-workers",
        type=int,
        default=1,
        help="Independent logical-record reconciliations to run concurrently",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser


def _flush_corpus_state(
    *,
    output_dir: Path,
    model_key: str,
    model_id: str,
    transcript: str,
    statuses: list[tuple[str, int | str]],
    sample_metadata: dict[str, dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    status_text = "sample\tstatus\n" + "".join(
        f"{sample}\t{status}\n" for sample, status in statuses
    )
    status_path = output_dir / "per_sample_status.tsv"
    temporary = status_path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(status_text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(status_path)
    _atomic_write_json(
        output_dir / "run_metadata.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runner": Path(__file__).name,
            "model_key": model_key,
            "model_id": model_id,
            "transcript": transcript,
            "sample_statuses": {sample: status for sample, status in statuses},
            "samples": sample_metadata,
        },
    )


def run_corpus(
    *,
    dataset_dir: Path,
    samples: list[str],
    transcript: str,
    output_dir: Path,
    model_key: str,
    client: BonsaiClient,
    resume: bool,
    document_attempts: int,
    validation_attempts: int = 3,
    page_workers: int = 1,
    reduction_workers: int = 1,
    run_document_fn: Callable[..., dict[str, Any]] = run_document,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[list[tuple[str, int | str]], dict[str, dict[str, Any]]]:
    if document_attempts < 1:
        raise ValueError("document_attempts must be at least 1")
    statuses: list[tuple[str, int | str]] = []
    sample_metadata: dict[str, dict[str, Any]] = {}
    existing_metadata_path = output_dir / "run_metadata.json"
    if resume and existing_metadata_path.is_file():
        try:
            existing = json.loads(
                existing_metadata_path.read_text(encoding="utf-8")
            )
            if isinstance(existing.get("samples"), dict):
                sample_metadata.update(existing["samples"])
        except (OSError, json.JSONDecodeError):
            pass

    for index, sample in enumerate(samples, start=1):
        print(f"[{index}/{len(samples)}] {sample}", flush=True)
        status: int | str = "not_started"
        document_metadata: dict[str, Any] | None = None
        for attempt in range(1, document_attempts + 1):
            try:
                document_metadata = run_document_fn(
                    dataset_dir=dataset_dir,
                    sample=sample,
                    transcript=transcript,
                    output_dir=output_dir,
                    model_key=model_key,
                    client=client,
                    resume=resume,
                    validation_attempts=validation_attempts,
                    page_workers=page_workers,
                    reduction_workers=reduction_workers,
                    sleep=sleep,
                )
                status = 0
                break
            except RetryableInferenceError as exc:
                status = f"retryable_error: {exc}"
                append_event(
                    output_dir,
                    {
                        "type": "document_retry",
                        "sample": sample,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )
                if attempt < document_attempts:
                    sleep(float(2 ** (attempt - 1)))
            except Exception as exc:
                status = f"error: {exc}"
                break
        statuses.append((sample, status))
        if document_metadata is not None:
            sample_metadata[sample] = document_metadata
        _flush_corpus_state(
            output_dir=output_dir,
            model_key=model_key,
            model_id=client.model_id,
            transcript=transcript,
            statuses=statuses,
            sample_metadata=sample_metadata,
        )
        print(f"  -> {status}", flush=True)
    return statuses, sample_metadata


def _require_power_mode() -> None:
    try:
        from .run_pi_local_evaluation import (
            macos_ac_power_mode,
            require_benchmark_power_mode,
        )
    except ImportError:
        from run_pi_local_evaluation import (
            macos_ac_power_mode,
            require_benchmark_power_mode,
        )
    require_benchmark_power_mode(macos_ac_power_mode())


def score_saved_predictions(
    *,
    models: list[str],
    samples: list[str],
    transcript: str,
    dataset_dir: Path,
    output_dir: Path,
) -> None:
    try:
        from .evaluate_models import (
            generate_report,
            run_evaluation_from_saved_predictions,
        )
    except ImportError:
        from evaluate_models import (
            generate_report,
            run_evaluation_from_saved_predictions,
        )
    results = run_evaluation_from_saved_predictions(
        models=models,
        samples=samples,
        transcripts=[transcript],
        claims_dir=dataset_dir,
        output_dir=output_dir,
    )
    generate_report(results, output_dir, evaluation_mode="saved_predictions")


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    _require_power_mode()
    dataset_dir = Path(args.dataset_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    samples = discover_samples(dataset_dir, args.samples)
    api_key = "local"
    if args.api_key_env is not None:
        api_key = os.environ.get(args.api_key_env, "")
        if not api_key:
            raise SystemExit(
                f"Environment variable {args.api_key_env!r} is not set"
            )
    client = BonsaiClient(
        endpoint=args.endpoint,
        model_id=args.model,
        max_attempts=args.max_attempts,
        timeout_seconds=args.timeout_seconds,
        api_key=api_key,
    )
    statuses, _metadata = run_corpus(
        dataset_dir=dataset_dir,
        samples=samples,
        transcript=args.transcript,
        output_dir=output_dir,
        model_key=args.model_key,
        client=client,
        resume=args.resume,
        document_attempts=args.document_attempts,
        validation_attempts=args.validation_attempts,
        page_workers=args.page_workers,
        reduction_workers=args.reduction_workers,
    )
    score_saved_predictions(
        models=[args.model_key],
        samples=samples,
        transcript=args.transcript,
        dataset_dir=dataset_dir,
        output_dir=output_dir,
    )
    return 0 if all(status == 0 for _sample, status in statuses) else 1


_PAGE_HEADING = re.compile(r"(?m)^# Page (\d+)[ \t]*\n")


def split_ocr_pages(transcript: str) -> list[Page]:
    matches = list(_PAGE_HEADING.finditer(transcript))
    if not matches:
        raise ValueError("OCR transcript does not contain '# Page N' headings")

    pages: list[Page] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(transcript)
        page_text = transcript[match.start() : end].rstrip() + "\n"
        pages.append(Page(number=int(match.group(1)), text=page_text))
    return pages


if __name__ == "__main__":
    raise SystemExit(main())
