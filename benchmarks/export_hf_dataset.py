#!/usr/bin/env python3
"""Package LongListBench as a Hugging Face datasets repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

try:
    from .evaluation_roles import SCALE_CONTROL_REGIMES, evaluation_role
except ImportError:
    from evaluation_roles import SCALE_CONTROL_REGIMES, evaluation_role


DEFAULT_REPO_ID = "kaydotai/LongListBench"
DATASET_DOI = "10.57967/hf/9768"
RELEASE_VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()
DEFAULT_BASELINE_REPORTS = (
    Path(__file__).resolve().parent / "results" / "codex_gpt56_sol_full_current_ocr_v2" / "evaluation_report.json",
    Path(__file__).resolve().parent / "results" / "claude_fable5_full_current_ocr_v2" / "evaluation_report.json",
    Path(__file__).resolve().parent / "results" / "codex_full_current_ocr_v2" / "evaluation_report.json",
    Path(__file__).resolve().parent / "results" / "claude_opus48_full_current_ocr_v2" / "evaluation_report.json",
)
DEFAULT_BASELINE_REPORT = DEFAULT_BASELINE_REPORTS[0]
CONFIG_ORDER = ("core_operations", "claim_multihop", "policy_packets")
CONFIG_DESCRIPTIONS = {
    "core_operations": "26 production-like commercial insurance and trucking PDFs with dense repeated operations, IFTA, and loss-run records.",
    "claim_multihop": "3 long claim PDFs where incident records must be assembled from distant sections.",
    "policy_packets": "3 long Businessowners, Workers Compensation, and Commercial General Liability policy packets where records must be assembled from distant sections.",
}

CLAIM_TARGET_TYPES = {"loss_run_incident"}
BASELINE_MODEL_KEY = "codex_gpt55"
BASELINE_PRESENTATIONS = {
    "codex_gpt56_sol": {
        "label": "Codex CLI `gpt-5.6-sol`, xhigh reasoning",
        "family_label": "GPT-5.6-Sol exact records",
    },
    "claude_fable5": {
        "label": "Claude Code CLI `claude-fable-5`, xhigh effort",
        "family_label": "Fable 5 exact records",
    },
    "codex_gpt55": {
        "label": "Codex CLI `gpt-5.5`, xhigh reasoning",
        "family_label": "GPT-5.5 exact records",
    },
    "claude_opus48": {
        "label": "Claude Code CLI `claude-opus-4-8`, xhigh effort",
        "family_label": "Opus 4.8 exact records",
    },
}
BASELINE_REGIMES = (
    ("driver_mvr_request_and_roster", "Sparse record enrichment (driver/MVR)"),
    ("claim_crosspage_multihop", "Long-range claim joins"),
    ("ifta_return_schedule_details", "Split return schedules"),
    ("loss_run_external", "Mixed row/detail loss runs"),
    ("ifta_tax_return_inquiry_detail", "Tax inquiry detail tables"),
    ("policy_multi_hop", "Heterogeneous policy records"),
    ("ifta_multisection_return_packet", "Cross-section return joins"),
    ("ifta_tax_return_summary", "Tax-summary scale controls"),
    ("driver_schedule_spreadsheet_export", "Driver-schedule scale control"),
    ("ifta_mileage_by_vehicle", "Mileage-by-vehicle scale controls"),
    ("vehicle_schedule_spreadsheet_export", "Vehicle-schedule scale controls"),
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sample_id(instance: dict[str, Any]) -> str:
    value = instance.get("id") or instance.get("instance_id")
    if not value:
        raise ValueError(f"Manifest instance is missing id: {instance}")
    return str(value)


def instance_domain(instance: dict[str, Any]) -> str:
    return str(instance.get("domain") or "claims")


def target_record_type(instance: dict[str, Any]) -> str:
    if instance.get("target_record_type"):
        return str(instance["target_record_type"])
    if instance_domain(instance) == "policy_review":
        return "policy_packet_item"
    return "loss_run_incident"


def target_field(instance: dict[str, Any]) -> str:
    if target_record_type(instance) in CLAIM_TARGET_TYPES or instance_domain(instance) == "claims":
        return "incidents"
    return "records"


def target_count(instance: dict[str, Any], ground_truth: list[Any]) -> int:
    for key in ("num_target_records", "num_policy_items", "num_claims"):
        value = instance.get(key)
        if isinstance(value, int):
            return value
    return len(ground_truth)


def page_count(instance: dict[str, Any]) -> int:
    for key in ("pdf_page_count", "pages_estimate"):
        value = instance.get(key)
        if isinstance(value, int):
            return value
    return 0


def config_for_instance(instance: dict[str, Any]) -> str:
    if instance_domain(instance) == "policy_review":
        return "policy_packets"
    if instance_domain(instance) == "claims" and instance.get("format") == "crosspage":
        return "claim_multihop"
    return "core_operations"


def resolve_artifact(dataset_dir: Path, instance: dict[str, Any], artifact: str) -> Path:
    files = instance.get("files") or {}
    relative = files.get(artifact)
    if not relative:
        raise ValueError(f"{sample_id(instance)} is missing files.{artifact}")
    path = dataset_dir / relative
    if not path.exists():
        raise FileNotFoundError(f"Missing {artifact} for {sample_id(instance)}: {path}")
    return path


def optional_transcript(dataset_dir: Path, instance: dict[str, Any], artifact: str) -> str:
    files = instance.get("files") or {}
    relative = files.get(artifact)
    if not relative:
        return ""
    path = dataset_dir / relative
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def row_for_instance(dataset_dir: Path, instance: dict[str, Any]) -> dict[str, Any]:
    sid = sample_id(instance)
    gt_path = resolve_artifact(dataset_dir, instance, "ground_truth")
    pdf_path = resolve_artifact(dataset_dir, instance, "pdf")
    ground_truth = read_json(gt_path)
    if not isinstance(ground_truth, list):
        raise ValueError(f"{sid} ground truth must be a list, got {type(ground_truth).__name__}")

    normalized_target_field = target_field(instance)
    complexity_regime = str(instance.get("complexity_regime") or instance.get("difficulty") or "")
    metadata = {
        "manifest_instance": instance,
        "source_files": instance.get("files", {}),
        "ground_truth_sha256": sha256_file(gt_path),
        "pdf_sha256": sha256_file(pdf_path),
    }

    return {
        "document_id": sid,
        "complexity_regime": complexity_regime,
        "evaluation_role": evaluation_role(complexity_regime),
        "num_pages": page_count(instance),
        "target_field": normalized_target_field,
        "target_record_type": target_record_type(instance),
        "target_count": target_count(instance, ground_truth),
        "stressors": list(instance.get("problems") or []),
        "pdf": {"path": f"{sid}.pdf", "bytes": pdf_path.read_bytes()},
        "ground_truth": canonical_json({normalized_target_field: ground_truth}),
        "metadata": canonical_json(metadata),
        "ocr_transcript": optional_transcript(dataset_dir, instance, "ocr_md"),
    }


def build_config_rows(dataset_dir: Path) -> dict[str, list[dict[str, Any]]]:
    manifest = read_json(dataset_dir / "manifest.json")
    rows_by_config: dict[str, list[dict[str, Any]]] = {name: [] for name in CONFIG_ORDER}
    for instance in manifest["instances"]:
        rows_by_config[config_for_instance(instance)].append(row_for_instance(dataset_dir, instance))
    return rows_by_config


def summarize_rows(rows_by_config: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for config_name in CONFIG_ORDER:
        rows = rows_by_config.get(config_name, [])
        page_counts = [row["num_pages"] for row in rows]
        target_counts = [row["target_count"] for row in rows]
        target_fields = sorted(set(row["target_field"] for row in rows))
        summary[config_name] = {
            "rows": len(rows),
            "targets": sum(target_counts),
            "min_targets": min(target_counts) if target_counts else 0,
            "max_targets": max(target_counts) if target_counts else 0,
            "min_pages": min(page_counts) if page_counts else 0,
            "max_pages": max(page_counts) if page_counts else 0,
            "target_fields": target_fields,
        }
    return summary


def load_release_baseline(
    report_path: Path,
    dataset_dir: Path,
    model_key: str | None = None,
) -> dict[str, Any]:
    """Load the released baseline and verify that it targets this manifest."""
    report = read_json(report_path)
    provenance = report.get("dataset") or {}
    expected_manifest_hash = sha256_file(dataset_dir / "manifest.json")
    if provenance.get("manifest_sha256") != expected_manifest_hash:
        raise ValueError(
            "Baseline report manifest hash does not match the dataset being exported: "
            f"{report_path}"
        )

    all_model_stats = report.get("model_stats") or {}
    if model_key is None:
        if len(all_model_stats) != 1:
            raise ValueError(
                f"Baseline report must contain exactly one model or specify model_key: {report_path}"
            )
        model_key = next(iter(all_model_stats))
    model_stats = all_model_stats.get(model_key)
    if not isinstance(model_stats, dict):
        raise ValueError(f"Baseline report is missing model_stats.{model_key}: {report_path}")
    if model_key not in BASELINE_PRESENTATIONS:
        raise ValueError(f"No dataset-card presentation is registered for baseline model {model_key}")

    return {
        "report_path": report_path,
        "report": report,
        "model_stats": model_stats,
        "model_key": model_key,
        "presentation": BASELINE_PRESENTATIONS[model_key],
    }


def _baseline_list(
    baselines: dict[str, Any] | list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[dict[str, Any]]:
    if baselines is None:
        return []
    if isinstance(baselines, dict):
        return [baselines]
    return list(baselines)


def _headline_finding(
    baselines: dict[str, Any] | list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> str:
    baseline_list = _baseline_list(baselines)
    if not baseline_list:
        return ""

    sample_counts = {baseline["model_stats"]["total_samples"] for baseline in baseline_list}
    if len(sample_counts) != 1:
        raise ValueError("Baseline reports disagree on total sample count")

    field_f1 = [baseline["model_stats"]["weighted_f1"] for baseline in baseline_list]
    complete = [baseline["model_stats"]["complete_documents"] for baseline in baseline_list]
    sample_count = next(iter(sample_counts))
    field_f1_text = (
        f"field micro-F1 is {field_f1[0]:.1%}"
        if min(field_f1) == max(field_f1)
        else f"field micro-F1 ranges from {min(field_f1):.1%} to {max(field_f1):.1%}"
    )
    complete_text = (
        str(complete[0])
        if min(complete) == max(complete)
        else f"{min(complete)}-{max(complete)}"
    )
    run_word = "run" if len(baseline_list) == 1 else "runs"
    return (
        f"Across the {len(baseline_list)} released agent {run_word}, {field_f1_text}, "
        f"but only {complete_text} of {sample_count} documents "
        "are complete."
    )


def _baseline_section(
    baselines: dict[str, Any] | list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> str:
    baseline_list = _baseline_list(baselines)
    if not baseline_list:
        return ""

    overall_rows = []
    for baseline in baseline_list:
        stats = baseline["model_stats"]
        presentation = baseline.get("presentation") or BASELINE_PRESENTATIONS[BASELINE_MODEL_KEY]
        overall_rows.append(
            f"| {presentation['label']} | {stats['total_samples']} | {stats['total_rows']:,} | "
            f"{stats['errors']} | {stats['exact_record_recall']:.1%} | "
            f"{stats['complete_documents']}/{stats['total_samples']} ({stats['complete_document_rate']:.1%}) | "
            f"{stats['weighted_f1']:.1%} | {stats['avg_f1']:.1%} |"
        )

    family_headers = [
        (baseline.get("presentation") or BASELINE_PRESENTATIONS[BASELINE_MODEL_KEY])["family_label"]
        for baseline in baseline_list
    ]
    regime_rows = []
    for regime_key, label in BASELINE_REGIMES:
        regimes = []
        for baseline in baseline_list:
            regime = (baseline["model_stats"].get("by_complexity_regime") or {}).get(regime_key)
            if not isinstance(regime, dict):
                raise ValueError(f"Baseline report is missing document-family metrics: {regime_key}")
            regimes.append(regime)
        first_regime = regimes[0]
        if any(
            regime["count"] != first_regime["count"] or regime["rows"] != first_regime["rows"]
            for regime in regimes[1:]
        ):
            raise ValueError(f"Baseline reports disagree on document-family coverage: {regime_key}")
        regime_rows.append(
            f"| {label} | "
            f"{'Scale control' if regime_key in SCALE_CONTROL_REGIMES else 'Structural challenge'} | "
            f"{first_regime['count']} | {first_regime['rows']:,} | "
            + " | ".join(f"{regime['exact_record_recall']:.1%}" for regime in regimes)
            + " |"
        )

    role_rows = []
    for role_key, role_label in (
        ("structural_challenge", "Structural challenges"),
        ("scale_control", "Scale controls"),
    ):
        role_stats = []
        for baseline in baseline_list:
            role = (baseline["model_stats"].get("by_evaluation_role") or {}).get(role_key)
            if not isinstance(role, dict):
                raise ValueError(f"Baseline report is missing evaluation-role metrics: {role_key}")
            role_stats.append(role)
        first_role = role_stats[0]
        if any(
            role["count"] != first_role["count"] or role["rows"] != first_role["rows"]
            for role in role_stats[1:]
        ):
            raise ValueError(f"Baseline reports disagree on evaluation-role coverage: {role_key}")
        role_rows.append(
            f"| {role_label} | {first_role['count']} | {first_role['rows']:,} | "
            + " | ".join(f"{role['exact_record_recall']:.1%}" for role in role_stats)
            + " |"
        )

    result_dir_names = [
        Path(baseline["report_path"]).parent.name
        if baseline.get("report_path")
        else (
            "claude_opus48_full_current_ocr_v2"
            if baseline.get("model_key") == "claude_opus48"
            else "codex_full_current_ocr_v2"
        )
        for baseline in baseline_list
    ]
    links = ", ".join(
        f"[{name}](./evaluation/{name}/)" for name in result_dir_names
    )
    return f"""## Current Baselines

The release includes {len(baseline_list)} full-corpus OCR-conditioned agentic baselines; the models and settings are listed below. Each received the OCR transcript, public field contract, and extraction prompt in a repository-denied workspace. Ground truth and target counts were unavailable.

Strict completeness on the released OCR transcripts:

| Protocol | Documents | Target records | Errors | Exact-record recall | Complete documents | Field micro-F1 | Field macro-F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(overall_rows)}

The split between parser-friendly scale controls and structural challenges is visible below:

| Evaluation role | Documents | Target records | {' | '.join(family_headers)} |
|---|---:|---:|{'|'.join(['---:'] * len(family_headers))}|
{chr(10).join(role_rows)}

Exact-record recall by extraction problem shows why aggregate scores should not be interpreted alone:

| Extraction problem | Evaluation role | Documents | Target records | {' | '.join(family_headers)} |
|---|---|---:|---:|{'|'.join(['---:'] * len(family_headers))}|
{chr(10).join(regime_rows)}

Saved predictions and reports in {links} reproduce these metrics without model access. Run metadata records the dataset hash, prompt, model settings, runtime, and output hash.
"""


def write_parquet_export(rows_by_config: dict[str, list[dict[str, Any]]], output_dir: Path) -> None:
    try:
        from datasets import Dataset, Features, Pdf, Sequence, Value
    except ImportError as exc:
        raise SystemExit(
            "Missing Hugging Face export dependencies. "
            "Install them with: python -m pip install -r benchmarks/requirements-hf.txt"
        ) from exc

    features = Features(
        {
            "document_id": Value("string"),
            "complexity_regime": Value("string"),
            "evaluation_role": Value("string"),
            "num_pages": Value("int32"),
            "target_field": Value("string"),
            "target_record_type": Value("string"),
            "target_count": Value("int32"),
            "stressors": Sequence(Value("string")),
            "pdf": Pdf(decode=False),
            "ground_truth": Value("string"),
            "metadata": Value("string"),
            "ocr_transcript": Value("string"),
        }
    )

    for config_name in CONFIG_ORDER:
        rows = rows_by_config.get(config_name, [])
        if not rows:
            continue
        config_dir = output_dir / "data" / config_name
        config_dir.mkdir(parents=True, exist_ok=True)
        dataset = Dataset.from_list(rows, features=features)
        dataset.to_parquet(config_dir / "test-00000-of-00001.parquet")


def write_metadata_files(dataset_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir = output_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dataset_dir / "manifest.json", metadata_dir / "manifest.json")
    numeric_baseline = dataset_dir / "ocr_numeric_fidelity_baseline.json"
    if numeric_baseline.exists():
        shutil.copy2(numeric_baseline, metadata_dir / numeric_baseline.name)

    schema_dir = output_dir / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    for schema_path in sorted((dataset_dir / "schemas").glob("*.schema.json")):
        shutil.copy2(schema_path, schema_dir / schema_path.name)


def write_evaluation_files(
    baselines: dict[str, Any] | list[dict[str, Any]] | tuple[dict[str, Any], ...],
    output_dir: Path,
) -> None:
    for baseline in _baseline_list(baselines):
        _write_evaluation_files_for_baseline(baseline, output_dir)


def _write_evaluation_files_for_baseline(baseline: dict[str, Any], output_dir: Path) -> None:
    report_path = Path(baseline["report_path"])
    report = baseline["report"]
    results_dir = report_path.parent
    target_dir = output_dir / "evaluation" / results_dir.name
    target_dir.mkdir(parents=True, exist_ok=True)

    detailed_results = report.get("detailed_results") or []
    status_lines = ["sample\tstatus"]
    for entry in detailed_results:
        status_lines.append(f"{entry['sample']}\t{1 if entry.get('error') else 0}")
        if entry.get("error"):
            continue
        prediction = results_dir / (
            f"{entry['sample']}_{entry.get('transcript', 'ocr')}_{entry['model']}_predicted.json"
        )
        if not prediction.exists():
            raise FileNotFoundError(f"Missing released baseline prediction: {prediction}")
        shutil.copy2(prediction, target_dir / prediction.name)

    source_status = results_dir / "per_sample_status.tsv"
    if source_status.exists():
        shutil.copy2(source_status, target_dir / source_status.name)
    else:
        (target_dir / "per_sample_status.tsv").write_text(
            "\n".join(status_lines) + "\n",
            encoding="utf-8",
        )

    for filename in ("README.md", "evaluation_report.json", "evaluation_report.md", "run_metadata.json"):
        source = results_dir / filename
        if source.exists():
            shutil.copy2(source, target_dir / source.name)


def dataset_card(
    repo_id: str,
    summary: dict[str, dict[str, Any]],
    baseline: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> str:
    config_yaml = "\n".join(
        [
            f"- config_name: {config_name}\n"
            "  data_files:\n"
            "  - split: test\n"
            f"    path: data/{config_name}/test-*.parquet"
            for config_name in CONFIG_ORDER
        ]
    )
    config_rows = "\n".join(
        [
            "| `{name}` | {description} | `{target_field}` | {rows} | {min_targets:,}-{max_targets:,} | {targets:,} | {min_pages:,}-{max_pages:,} |".format(
                name=config_name,
                description=CONFIG_DESCRIPTIONS[config_name],
                target_field="`, `".join(summary[config_name]["target_fields"]),
                **summary[config_name],
            )
            for config_name in CONFIG_ORDER
        ]
    )

    total_rows = sum(item["rows"] for item in summary.values())
    total_targets = sum(item["targets"] for item in summary.values())
    total_targets_text = f"{total_targets:,}"
    baseline_section = _baseline_section(baseline)
    headline_finding = _headline_finding(baseline)
    headline_suffix = f" {headline_finding}" if headline_finding else ""

    return f"""---
pretty_name: LongListBench
language:
- en
license: mit
tags:
- document-extraction
- benchmark
- synthetic
- pdf
- ocr
- document-ai
- information-extraction
- structured-extraction
- long-list-extraction
- long-array
- long-range-evidence
- insurance
- trucking
size_categories:
- n<1K
configs:
{config_yaml}
---

# LongListBench

[Paper](https://huggingface.co/datasets/{repo_id}/blob/main/longlistbench.pdf) | [GitHub](https://github.com/kaydotai/longlistbench) | [Release v{RELEASE_VERSION}](https://github.com/kaydotai/longlistbench/releases/tag/v{RELEASE_VERSION})

**Developed by [Kay.ai](https://kay.ai).**

**Authors:** [Anton Fedoruk](https://orcid.org/0009-0004-0260-1704), [Serhii Shchoholiev](https://orcid.org/0009-0007-2014-4828), [Akhil Mehta](https://orcid.org/0009-0001-0134-2905), and Vishal Rohra

Long-list extraction is not complete when most fields are right: an omitted, merged, or invented row can invalidate the document-level result.{headline_suffix}

LongListBench measures this failure mode in insurance and commercial trucking PDFs. A system receives one PDF or OCR transcript and a target contract, then returns the full target list. The release contains {total_rows} synthetic PDFs and {total_targets_text} target records; no real customer PII is included.

`core_operations` tests scale and output completeness. `claim_multihop` and `policy_packets` add inherited context, distant evidence, and mixed record schemas.

## Complexity Stressors

Each PDF records its extraction stressors under `stressors`:

| Tag | Meaning |
|---|---|
| `page_breaks` | Lists or supporting evidence continue across pages with repeated headers or inherited context. |
| `split_records` | One target record has fields in separate visual blocks, sections, or pages and must be assembled. |
| `multi_row` | Records include wrapped notes, descriptions, clauses, or continuation rows. |
| `duplicates` | Prior-term, archived, duplicate, or near-duplicate distractor material is present. |
| `large_doc` | The document is long enough to stress truncation and record-completeness behavior. |
| `multiple_tables` | Target rows are mixed with summaries, ledgers, schedules, support tables, or empty tables. |
| `multi_column` | Pages use two-column or form-like layouts that stress reading order. |
| `merged_cells` | Tables include section-spanning or merged-cell structures. |
| `ocr_condition` | The released text condition is OCR from rendered page images. |
| `ocr_layout_condition` | OCR preserves visual spacing and reading order instead of converting tables into clean CSV-style rows. |
| `long_range_evidence` | Fields must be joined from distant sections of one PDF. |
| `cross_section_join` | A target record must be assembled from separately labeled sections, such as return summary, distance/gallon schedules, and liability schedules. |
| `repeated_keys` | Common keys such as states or jurisdictions repeat across sections or returns, so the key alone is insufficient for matching. |
| `heterogeneous_record_list` | A target list contains several record schemas, especially in policy packets. |

These 14 tags are canonical. The release also retains finer audit tags, for 45 distinct `stressors` tokens in total. Labels are metadata, not text printed inside the PDFs.

The following families make the tags easy to inspect in the PDFs:

| Family or config | Stressors visible in the document |
|---|---|
| `ifta_mileage_by_vehicle` | Jurisdiction rows inherit unit headers while source notes interrupt page-spanning tables. |
| `ifta_multisection_return_packet` | Return headers and separate distance, fuel, and tax sections must be joined across pages; OCR preserves layout rather than clean rows. |
| `loss_run_external` | Claim rows are interleaved with descriptions, continuation notes, summaries, and empty-table distractors. |
| `claim_multihop` | Claim schedules are separated from supporting policy, driver, claimant, cause-code, and ledger sections. |
| `policy_packets` | The target mixes declarations, schedules, forms, endorsements, premiums, and clause prose. |

## Configs and Data Viewer

| Config | Description | Target field | Documents | Records/doc range | Target records | Page range |
|---|---|---|---:|---:|---:|---:|
{config_rows}

Pick one config when loading:

```python
from datasets import load_dataset

ds = load_dataset("{repo_id}", "core_operations", split="test")
# or "claim_multihop", or "policy_packets"
print(ds)  # each row is one PDF document
```

## Columns

| Column | Type | Description |
|---|---|---|
| `document_id` | string | Stable sample identifier, e.g. `ifta_mileage_by_vehicle_001` or `multihop_bop_012_001`. |
| `complexity_regime` | string | Document family, such as `ifta_mileage_by_vehicle`, `loss_run_external`, `claim_crosspage_multihop`, or `policy_multi_hop`. |
| `evaluation_role` | string | Preassigned interpretation role: `scale_control` or `structural_challenge`. |
| `num_pages` | int32 | Page count recorded by the generator. |
| `target_field` | string | Name of the top-level list to extract: `incidents` for claim multi-hop rows, `records` for operations, external loss-run, and policy rows. |
| `target_record_type` | string | Primary schema family, such as `vehicle_state_mileage_row`, `driver_record`, `loss_run_claim_row`, or `policy_packet_item`. |
| `target_count` | int32 | Number of target records in `ground_truth`. |
| `stressors` | list[string] | Stressor tags for the document, e.g. `high_density_long_list`, `production_like_layout`, or `long_range_evidence`. |
| `pdf` | Pdf | Embedded source PDF bytes. |
| `ground_truth` | string | JSON string containing the expected records under `target_field`. |
| `metadata` | string | JSON string with manifest metadata, file hashes, evidence maps, generation details, and source artifact paths. |
| `ocr_transcript` | string | OCR transcript generated from rendered PDF page images. |

`ground_truth` is the complete schema-shaped object for the extraction target. Claim multi-hop rows use `{{"incidents": [...]}}`; all other list families use `{{"records": [...]}}`.

Manifest fields not exposed as columns, such as the domain, rendered layout format, and available transcript conditions, remain available under `metadata.manifest_instance`. The `stressors` column is stored as `problems` in the manifest.

## Usage

```python
import json
from datasets import load_dataset
from datasets import Pdf

ds = load_dataset("{repo_id}", "claim_multihop", split="test")

# The Pdf feature may decode through pdfplumber on access. Disable decoding
# when you only need bytes, transcripts, or ground truth.
ds = ds.cast_column("pdf", Pdf(decode=False))

row = ds[0]
gt = json.loads(row["ground_truth"])
records = gt[row["target_field"]]
assert len(records) == row["target_count"]

with open(f"{{row['document_id']}}.pdf", "wb") as f:
    f.write(row["pdf"]["bytes"])
```

## Canonical Scoring

The tagged [reference evaluator](https://github.com/kaydotai/longlistbench/blob/v{RELEASE_VERSION}/benchmarks/evaluation_metrics.py) defines official scoring. Strict normalized-record completeness is primary; field overlap is a secondary diagnostic.

### Method

1. Run the extractor on each PDF or transcript and return an object matching `ground_truth`: `{{"incidents": [...]}}` for claim multi-hop rows or `{{"records": [...]}}` for other families. The evaluator also accepts a bare list.
2. Claim incidents are keyed by normalized `incident_number`. Strings, dates, claimant lists, and non-zero financial breakdowns use documented canonical forms.
3. Other records normalize case, whitespace, dates, numeric formatting, accounting negatives, and documented label equivalents. Exact records are anchored before field-overlap matching; strict comparison still uses every public target field.
4. Exact-record recall is `exact_record_matches / ground_truth_count`. A document is complete only when the predicted and gold record multisets are identical, including duplicates and with no extra records. Record order is not scored.
5. Field recall and precision compare flattened field-value pairs; F1 is their harmonic mean. Document-macro and corpus-micro field F1 show partial correctness, not complete-list recovery.

Clone the matching release before running the example so the canonical evaluator is importable:

```bash
git clone --branch v{RELEASE_VERSION} --depth 1 https://github.com/kaydotai/longlistbench.git
cd longlistbench
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r benchmarks/requirements-hf.txt "pydantic>=2.5.0"
```

Run the scoring example from the repository root. The benchmark checkout is a source tree, not an installed Python package.

```python
import json
from datasets import load_dataset
from benchmarks.evaluation_metrics import (
    evaluate_extraction,
    evaluate_record_extraction,
    normalize_record_predictions,
    uses_record_evaluator,
)

config = "policy_packets"
ds = load_dataset("{repo_id}", config, split="test")

for row in ds.remove_columns("pdf"):
    gold = json.loads(row["ground_truth"])
    pred = my_predictions[row["document_id"]]
    gold_rows = gold[row["target_field"]]
    pred_rows = normalize_record_predictions(pred)
    metrics = (
        evaluate_record_extraction(pred_rows, gold_rows)
        if uses_record_evaluator(gold_rows)
        else evaluate_extraction(pred_rows, gold_rows)
    )
    print(
        row["document_id"],
        metrics["exact_record_recall"],
        metrics["complete_document"],
        metrics["f1"],
    )
```

{baseline_section}
## Schemas

Extraction schemas are published as standalone JSON Schema files under [`schemas/`](./schemas):

- [`schemas/loss_run_incident.schema.json`](./schemas/loss_run_incident.schema.json) - `incidents[]` for claim multi-hop incident rows, including incident identifiers, policy fields, claimant/driver fields, dates, coverage fields, and nested financial breakdowns.
- [`schemas/loss_run_claim_row.schema.json`](./schemas/loss_run_claim_row.schema.json) - `records[]` for external loss-run schedule rows in the core operations config.
- [`schemas/ifta_multisection_jurisdiction_row.schema.json`](./schemas/ifta_multisection_jurisdiction_row.schema.json) - `records[]` for multisection IFTA return rows assembled from return headers, Schedule A mileage/gallon rows, and Jurisdictions tax-detail rows.
- [`schemas/policy_packet_item.schema.json`](./schemas/policy_packet_item.schema.json) - `records[]` for BOP/WC/CGL policy packet rows. Records are heterogeneous and may represent locations, coverages, forms, material clauses, endorsements, exclusions, rating rows, or premium items depending on `record_type`.

These schemas describe the strict claim, external loss-run, multisection IFTA, and policy extraction targets. Other operations rows are represented by their ground-truth field contracts and the generic record-list scorer.

## Transcript Conditions

The current release includes OCR transcripts for every PDF:

- `ocr_transcript`: OCR text generated from 200-DPI rendered PDF page images with Google Gemini 3.5 Flash vision OCR through the direct Vertex AI API.

OCR validation reports 100.0% average identifier coverage and 100.0% tracked identifier-field support, with no records missing a tracked identifier. A separate audit finds 56 genuine OCR misses among 76,968 checked numeric fields with absolute value at least 10 (0.073%). The transcript is not hand-corrected; [`metadata/ocr_numeric_fidelity_baseline.json`](./metadata/ocr_numeric_fidelity_baseline.json) records the exact audited miss set. Interpret OCR-conditioned extraction scores with this ceiling in mind.

## Provenance

The documents are synthetic. Each sample follows this generation workflow:

1. Deterministic fixtures create the schema-shaped ground truth.
2. Layout generators place those records into document-specific tables and narrative sections.
3. HTML/CSS rendering produces the source PDF.
4. OCR over rendered page images produces the released transcript for each PDF.

Policy packets follow commercial insurance structures, but all content and identifiers are synthetic.

HF rows embed the PDF, OCR transcript, ground truth, and metadata. Tagged GitHub releases also retain the rendered HTML. Private template tooling used for the current layouts is not public, so the release does not claim bit-for-bit PDF regeneration.

No customer documents or real insured, claimant, policy, or account data are included. Real documents were used only as structural references for layout and packet organization.

## Limitations

LongListBench is not a substitute for evaluation on a private production corpus. Synthetic documents can underrepresent the visual and linguistic diversity of real carrier packets.

Some structured-report families are parser-friendly by design and serve as scale/completeness controls rather than hard semantic cases. Parser-transfer baselines remain useful diagnostics, but the main task allows a system to inspect each document and choose its extraction strategy. OCR support should be interpreted per affected record: one missing section header can affect many rows even when their identifiers remain visible.

## License

[MIT](https://github.com/kaydotai/longlistbench/blob/main/LICENSE). The documents and ground truth are synthetic and released with the repository under this license.

## Citation

```bibtex
@misc{{fedoruk2026longlistbench,
  title        = {{LongListBench: A Benchmark for Long-List Entity Extraction from Complex Business PDFs}},
  author       = {{Fedoruk, Anton and Shchoholiev, Serhii and Mehta, Akhil and Rohra, Vishal}},
  publisher    = {{Kay.ai}},
  year         = {{2026}},
  version      = {{{RELEASE_VERSION}}},
  howpublished = {{Hugging Face dataset}},
  doi          = {{{DATASET_DOI}}},
  url          = {{https://huggingface.co/datasets/{repo_id}}}
}}
```
"""


def write_dataset_card(
    output_dir: Path,
    repo_id: str,
    summary: dict[str, dict[str, Any]],
    baseline: dict[str, Any] | list[dict[str, Any]],
) -> None:
    (output_dir / "README.md").write_text(
        dataset_card(repo_id, summary, baseline),
        encoding="utf-8",
    )


def upload_to_hub(output_dir: Path, repo_id: str) -> None:
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise SystemExit(
            "Missing huggingface_hub. Install with: python -m pip install -r benchmarks/requirements-hf.txt"
        ) from exc

    api = HfApi()
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
    api.upload_folder(repo_id=repo_id, repo_type="dataset", folder_path=output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data"), help="Input data directory.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist/huggingface/longlistbench"),
        help="Output directory for the Hugging Face dataset package.",
    )
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID, help="Target Hugging Face dataset repo ID.")
    parser.add_argument(
        "--baseline-report",
        type=Path,
        nargs="+",
        default=list(DEFAULT_BASELINE_REPORTS),
        help="Released evaluation report(s) used to populate and package dataset-card baselines.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Remove the output directory before writing.")
    parser.add_argument("--upload", action="store_true", help="Upload the generated package to Hugging Face Hub.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_dir = args.input
    output_dir = args.output

    if args.overwrite and output_dir.exists():
        shutil.rmtree(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"Output directory is not empty: {output_dir}. Use --overwrite.")

    rows_by_config = build_config_rows(dataset_dir)
    summary = summarize_rows(rows_by_config)
    baselines = [load_release_baseline(path, dataset_dir) for path in args.baseline_report]
    write_parquet_export(rows_by_config, output_dir)
    write_metadata_files(dataset_dir, output_dir)
    write_evaluation_files(baselines, output_dir)
    write_dataset_card(output_dir, args.repo_id, summary, baselines)

    print(json.dumps({"output": str(output_dir), "repo_id": args.repo_id, "configs": summary}, indent=2))
    if args.upload:
        upload_to_hub(output_dir, args.repo_id)


if __name__ == "__main__":
    main()
