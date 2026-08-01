import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATHS = {
    "codex_gpt56_sol": ROOT
    / "benchmarks/results/codex_gpt56_sol_full_current_ocr_v2/evaluation_report.json",
    "codex_gpt56_terra": ROOT
    / "benchmarks/results/codex_gpt56_terra_full_current_ocr_v2/evaluation_report.json",
    "codex_gpt56_luna": ROOT
    / "benchmarks/results/codex_gpt56_luna_full_current_ocr_v2/evaluation_report.json",
    "claude_fable5": ROOT
    / "benchmarks/results/claude_fable5_full_current_ocr_v2/evaluation_report.json",
    "codex_gpt55": ROOT
    / "benchmarks/results/codex_full_current_ocr_v2/evaluation_report.json",
    "claude_opus48": ROOT
    / "benchmarks/results/claude_opus48_full_current_ocr_v2/evaluation_report.json",
}
RUN_EXPECTATIONS = {
    "codex_gpt56_sol": ("gpt-5.6-sol", "sample_statuses"),
    "codex_gpt56_terra": ("gpt-5.6-terra", "sample_statuses"),
    "codex_gpt56_luna": ("gpt-5.6-luna", "sample_statuses"),
    "claude_fable5": ("claude-fable-5", "samples"),
    "codex_gpt55": ("gpt-5.5", "sample_statuses"),
    "claude_opus48": ("claude-opus-4-8", "samples"),
}

OVERALL_LABELS = {
    "codex_gpt56_sol": (
        "Codex CLI `gpt-5.6-sol`, xhigh",
        "Codex CLI, GPT-5.6-Sol (xhigh)",
    ),
    "claude_fable5": (
        "Claude Code `claude-fable-5`, xhigh",
        "Claude Code, Fable 5 (xhigh)",
    ),
    "codex_gpt55": (
        "Codex CLI `gpt-5.5`, xhigh",
        "Codex CLI, GPT-5.5 (xhigh)",
    ),
    "claude_opus48": (
        "Claude Code `claude-opus-4-8`, xhigh",
        "Claude Code, Opus 4.8 (xhigh)",
    ),
}

LEADERBOARD_ONLY_LABELS = {
    "codex_gpt56_terra": "Codex CLI `gpt-5.6-terra`, xhigh",
    "codex_gpt56_luna": "Codex CLI `gpt-5.6-luna`, xhigh",
}

PROBLEM_LABELS = {
    "driver_mvr_request_and_roster": "Sparse record enrichment (driver/MVR)",
    "claim_crosspage_multihop": "Long-range claim joins",
    "ifta_return_schedule_details": "Split return schedules",
    "loss_run_external": "Mixed row/detail loss runs",
    "ifta_tax_return_inquiry_detail": "Tax inquiry detail tables",
    "policy_multi_hop": "Heterogeneous policy records",
    "ifta_multisection_return_packet": "Cross-section return joins",
    "ifta_tax_return_summary": "Tax-summary scale controls",
    "driver_schedule_spreadsheet_export": "Driver-schedule scale control",
    "ifta_mileage_by_vehicle": "Mileage-by-vehicle scale controls",
    "vehicle_schedule_spreadsheet_export": "Vehicle-schedule scale controls",
}

STRESSOR_LABELS = {
    "split_records": "Split records",
    "cross_section_join": "Cross-section joins",
    "repeated_keys": "Repeated keys",
    "long_range_evidence": "Long-range evidence",
    "heterogeneous_record_list": "Heterogeneous record lists",
    "page_breaks": "Page-spanning content",
    "multi_row": "Multi-row records",
    "merged_cells": "Merged cells (horizontal spans only)",
    "multiple_tables": "Multiple tables",
    "multi_column": "Multi-column pages",
    "duplicates": "Near-duplicate distractors (no true target duplicates)",
    "large_doc": "Large documents",
    "ocr_condition": "OCR input",
    "ocr_layout_condition": "OCR-preserved multi-section layout",
}

REQUIRED_SAMPLE_PROVENANCE = {
    "dataset_manifest_sha256",
    "runner_source_sha256",
    "transcript_sha256",
    "field_contract_sha256",
    "prompt_sha256",
    "input_fingerprint_sha256",
    "prediction_sha256",
}


def _load_stats(path: Path, expected_key: str) -> tuple[dict, dict]:
    report = json.loads(path.read_text(encoding="utf-8"))
    assert list(report["model_stats"]) == [expected_key]
    return report, report["model_stats"][expected_key]


def _pct(value: float) -> str:
    return f"{value:.1%}"


def _tex_int(value: int) -> str:
    return f"{value:,}".replace(",", "{,}")


def _tex_pct(value: float) -> str:
    return _pct(value).replace("%", r"\%")


def test_release_tables_match_saved_reports() -> None:
    loaded = {
        key: _load_stats(path, key)
        for key, path in REPORT_PATHS.items()
    }
    reports = {key: value[0] for key, value in loaded.items()}
    stats = {key: value[1] for key, value in loaded.items()}
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    abstract = (ROOT / "paper/contents/0_abstract.tex").read_text(encoding="utf-8")
    results_tex = (ROOT / "paper/contents/5_results.tex").read_text(encoding="utf-8")
    conclusion = (ROOT / "paper/contents/7_conclusion.tex").read_text(encoding="utf-8")
    manifest_path = ROOT / "data/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    expected_samples = Counter(str(instance["id"]) for instance in manifest["instances"])

    manifest_hashes = {report["dataset"]["manifest_sha256"] for report in reports.values()}
    assert manifest_hashes == {current_manifest_hash}
    sample_counts = {model_stats["total_samples"] for model_stats in stats.values()}
    row_counts = {model_stats["total_rows"] for model_stats in stats.values()}
    assert len(sample_counts) == 1
    assert len(row_counts) == 1
    total_samples = sample_counts.pop()
    total_rows = row_counts.pop()
    assert total_samples == manifest["total_documents"]
    assert total_rows == manifest["total_target_records"]
    assert f"{total_samples} synthetic PDFs" in abstract
    assert _tex_int(total_rows) in abstract
    for report in reports.values():
        assert report["dataset"]["git_dirty"] is False
        assert Counter(entry["sample"] for entry in report["detailed_results"]) == expected_samples
    for model_stats in stats.values():
        assert model_stats["total_samples"] == total_samples
        assert model_stats["total_rows"] == total_rows
        assert model_stats["errors"] == 0

    for key, (requested_model, sample_field) in RUN_EXPECTATIONS.items():
        metadata_path = REPORT_PATHS[key].with_name("run_metadata.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata["model_key"] == key
        assert metadata["requested_model"] == requested_model
        assert metadata["effort"] == "xhigh"
        assert metadata["transcript"] == "ocr"
        sample_metadata = metadata[sample_field]
        assert len(sample_metadata) == total_samples
        if sample_field == "sample_statuses":
            assert set(sample_metadata.values()) <= {0, "attest"}
        observed_samples = metadata["samples"]
        assert len(observed_samples) == total_samples
        for sample_id, sample in observed_samples.items():
            assert REQUIRED_SAMPLE_PROVENANCE <= sample.keys()
            for field in REQUIRED_SAMPLE_PROVENANCE:
                assert len(sample[field]) == 64
                int(sample[field], 16)
            prediction_path = REPORT_PATHS[key].parent / (
                f"{sample_id}_ocr_{key}_predicted.json"
            )
            assert hashlib.sha256(prediction_path.read_bytes()).hexdigest() == sample["prediction_sha256"]
            if sample_field == "sample_statuses":
                assert sample["observed_model"] == requested_model
                assert sample["observed_effort"] == "xhigh"
            else:
                assert sample["requested_model"] == requested_model
                assert sample["effort"] == "xhigh"
                assert requested_model in sample["matching_inference_models"]

        status_path = REPORT_PATHS[key].with_name("per_sample_status.tsv")
        statuses = {
            line.split("\t", 1)[1]
            for line in status_path.read_text(encoding="utf-8").splitlines()[1:]
        }
        assert statuses <= {"0", "attest"}
        assert statuses

    for key, (readme_label, tex_label) in OVERALL_LABELS.items():
        model_stats = stats[key]
        readme_row = (
            f"| {readme_label} | {total_samples} | {total_rows:,} | 0 | "
            f"{_pct(model_stats['exact_record_recall'])} | "
            f"{model_stats['complete_documents']}/{total_samples} "
            f"({_pct(model_stats['complete_document_rate'])}) | "
            f"{_pct(model_stats['weighted_f1'])} |"
        )
        assert readme_row in readme
        tex_row = (
            f"{tex_label} & {_tex_pct(model_stats['exact_record_recall'])} & "
            f"{model_stats['complete_documents']}/{total_samples} "
            f"({_tex_pct(model_stats['complete_document_rate'])}) & "
            f"{_tex_pct(model_stats['weighted_f1'])} & "
            f"{_tex_pct(model_stats['avg_f1'])} \\\\"
        )
        assert tex_row in results_tex

    for key, readme_label in LEADERBOARD_ONLY_LABELS.items():
        model_stats = stats[key]
        readme_row = (
            f"| {readme_label} | {total_samples} | {total_rows:,} | 0 | "
            f"{_pct(model_stats['exact_record_recall'])} | "
            f"{model_stats['complete_documents']}/{total_samples} "
            f"({_pct(model_stats['complete_document_rate'])}) | "
            f"{_pct(model_stats['weighted_f1'])} | "
            f"{_pct(model_stats['avg_f1'])} |"
        )
        assert readme_row in readme

    sol = stats["codex_gpt56_sol"]
    fable = stats["claude_fable5"]
    for role_key, role_label in (
        ("structural_challenge", "Structural challenges"),
        ("scale_control", "Scale controls"),
    ):
        sol_role = sol["by_evaluation_role"][role_key]
        fable_role = fable["by_evaluation_role"][role_key]
        assert sol_role["count"] == fable_role["count"]
        assert sol_role["rows"] == fable_role["rows"]
        readme_role = (
            f"| {role_label} | {sol_role['count']} | {sol_role['rows']:,} | "
            f"{_pct(sol_role['exact_record_recall'])} | "
            f"{_pct(fable_role['exact_record_recall'])} | "
            f"{sol_role['complete_documents']}/{sol_role['count']} "
            f"({_pct(sol_role['complete_document_rate'])}) | "
            f"{fable_role['complete_documents']}/{fable_role['count']} "
            f"({_pct(fable_role['complete_document_rate'])}) |"
        )
        assert readme_role in readme
        tex_role = (
            f"{role_label} & {sol_role['count']} & {_tex_int(sol_role['rows'])} & "
            f"{_tex_pct(sol_role['exact_record_recall'])} & "
            f"{_tex_pct(fable_role['exact_record_recall'])} & "
            f"{sol_role['complete_documents']}/{sol_role['count']} "
            f"({_tex_pct(sol_role['complete_document_rate'])}) & "
            f"{fable_role['complete_documents']}/{fable_role['count']} "
            f"({_tex_pct(fable_role['complete_document_rate'])}) \\\\"
        )
        assert tex_role in results_tex

    for family_key, label in PROBLEM_LABELS.items():
        sol_family = sol["by_complexity_regime"][family_key]
        fable_family = fable["by_complexity_regime"][family_key]
        assert sol_family["count"] == fable_family["count"]
        assert sol_family["rows"] == fable_family["rows"]
        readme_row = (
            f"| {label} | {sol_family['count']} | {sol_family['rows']:,} | "
            f"{_pct(sol_family['exact_record_recall'])} | "
            f"{_pct(fable_family['exact_record_recall'])} |"
        )
        assert readme_row in readme
        tex_row = (
            f"{label} & {sol_family['count']} & {_tex_int(sol_family['rows'])} & "
            f"{_tex_pct(sol_family['exact_record_recall'])} & "
            f"{_tex_pct(fable_family['exact_record_recall'])} \\\\"
        )
        assert tex_row in results_tex

    sol_stressors = sol["by_stressor"]
    fable_stressors = fable["by_stressor"]
    for stressor_key, label in STRESSOR_LABELS.items():
        sol_stressor = sol_stressors[stressor_key]
        fable_stressor = fable_stressors[stressor_key]
        assert sol_stressor["count"] == fable_stressor["count"]
        assert sol_stressor["rows"] == fable_stressor["rows"]
        tex_row = (
            f"{label} & {sol_stressor['count']} & {_tex_int(sol_stressor['rows'])} & "
            f"{_tex_pct(sol_stressor['exact_record_recall'])} & "
            f"{_tex_pct(fable_stressor['exact_record_recall'])} \\\\"
        )
        assert tex_row in results_tex

    assert (
        f"recover {_tex_pct(sol['exact_record_recall'])} and "
        f"{_tex_pct(fable['exact_record_recall'])} of records exactly"
    ) in abstract
    assert (
        f"reproduce only {sol['complete_documents']} and "
        f"{fable['complete_documents']} of {total_samples} complete document lists"
    ) in abstract
    assert (
        f"recover {_tex_pct(sol['exact_record_recall'])} and "
        f"{_tex_pct(fable['exact_record_recall'])} of target records exactly but complete only "
        f"{sol['complete_documents']} and {fable['complete_documents']} of "
        f"{total_samples} documents"
    ) in conclusion
