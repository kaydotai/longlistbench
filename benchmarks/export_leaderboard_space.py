#!/usr/bin/env python3
"""Build the static LongListBench leaderboard Space from saved evaluation reports."""

from __future__ import annotations

import argparse
import html as html_module
import json
import shutil
from pathlib import Path

DEFAULT_REPO_ID = "kaydotai/LongListBench-Leaderboard"
REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RELEASE_VERSION = "v" + (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
DEFAULT_OUTPUT = REPO_ROOT / "dist" / "huggingface" / "leaderboard_space"
REDUCTO_CREDIT_PRICE_USD = 0.015
PRICING_OBSERVED_DATE = "2026-07-28"
PROMPT_TEMPLATE_DIR = REPO_ROOT / "benchmarks" / "leaderboard_prompts"

AGENTIC_PROMPT_TEMPLATES = (
    {"title": "Task prompt — exact", "filename": "agentic_cli_task.txt"},
    {
        "title": "Field contract template — separate per-document input",
        "filename": "generated_field_contract.txt",
    },
)
AGENTIC_PROMPT_NOTE = (
    "Repository-denied agentic run over released OCR transcripts. "
    "Generic operations and policy samples received a generated field contract; "
    "claim samples received the published incident JSON Schema."
)

RUNS = (
    {
        "run_dir": "codex_gpt56_sol_full_current_ocr_v2",
        "key": "codex_gpt56_sol",
        "harness": "Codex CLI",
        "model": "GPT-5.6-Sol",
        "protocol": "Agentic CLI",
        "cost_source": "codex_api_equivalent",
        "prompt_templates": AGENTIC_PROMPT_TEMPLATES,
        "prompt_note": AGENTIC_PROMPT_NOTE,
        "cost_metadata_path": (
            REPO_ROOT
            / "benchmarks/cost_measurements/gpt56_sol_20260729/usage_summary.json"
        ),
    },
    {
        "run_dir": "claude_opus48_full_current_ocr_v2",
        "key": "claude_opus48",
        "harness": "Claude Code",
        "model": "Claude Opus 4.8",
        "protocol": "Agentic CLI",
        "cost_source": "claude_api_equivalent",
        "prompt_templates": AGENTIC_PROMPT_TEMPLATES,
        "prompt_note": AGENTIC_PROMPT_NOTE,
    },
    {
        "run_dir": "claude_fable5_full_current_ocr_v2",
        "key": "claude_fable5",
        "harness": "Claude Code",
        "model": "Claude Fable 5",
        "protocol": "Agentic CLI",
        "cost_source": "claude_api_equivalent",
        "prompt_templates": AGENTIC_PROMPT_TEMPLATES,
        "prompt_note": AGENTIC_PROMPT_NOTE,
    },
    {
        "run_dir": "codex_full_current_ocr_v2",
        "key": "codex_gpt55",
        "harness": "Codex CLI",
        "model": "GPT-5.5",
        "protocol": "Agentic CLI",
        "cost_source": "codex_api_equivalent",
        "prompt_templates": AGENTIC_PROMPT_TEMPLATES,
        "prompt_note": AGENTIC_PROMPT_NOTE,
        "cost_metadata_path": (
            REPO_ROOT
            / "benchmarks/cost_measurements/gpt55_20260729/usage_summary.json"
        ),
    },
    {
        "run_dir": "reducto_deep_extract_v3_targeted_prompt",
        "key": "reducto_deep_extract",
        "harness": "Reducto",
        "model": "Deep Extract v3 (test-set tuned)",
        "protocol": "Raw PDF · test-set tuned",
        "cost_source": "reducto_credits",
        "leaderboard_cost_override_usd": 10.08,
        "prompt_templates": (
            {
                "title": "Generated field contract",
                "filename": "generated_field_contract.txt",
            },
            {
                "title": "Test-set-tuned additions",
                "filename": "reducto_test_set_tuned_additions.txt",
            },
        ),
        "prompt_note": "Test-set tuned after observing benchmark failure modes.",
        "effort": "targeted fields",
        "requested_model": "v3",
        "cli_version": "Reducto API",
    },
    {
        "run_dir": "reducto_deep_extract_v3_strict_contract",
        "key": "reducto_deep_extract",
        "harness": "Reducto",
        "model": "Deep Extract v3 (strict contract)",
        "protocol": "Raw PDF · strict contract",
        "cost_source": "reducto_credits",
        "leaderboard_cost_override_usd": 11.02,
        "prompt_templates": (
            {
                "title": "Generated field contract",
                "filename": "generated_field_contract.txt",
            },
        ),
        "prompt_note": "Primary Reducto comparison condition.",
        "effort": "identical contract",
        "requested_model": "v3",
        "cli_version": "Reducto API",
    },
    {
        "run_dir": "bonsai_27b_together_page_pipeline_full",
        "key": "bonsai_27b_together_page_pipeline",
        "harness": "Local + Together AI",
        "model": "Bonsai 27B",
        "protocol": "Page pipeline",
        "cost_source": "hosted_free",
        "prompt_templates": (
            {
                "title": "Page extraction",
                "filename": "bonsai_page_extraction.txt",
            },
            {
                "title": "Record reduction",
                "filename": "bonsai_record_reduction.txt",
            },
        ),
        "prompt_note": "Two-stage page pipeline over released OCR transcripts.",
        "effort": "page pipeline",
        "requested_model": "Prism-ML/Ternary-Bonsai-27B",
        "cli_version": "Together API",
    },
)
SPACE_FILENAMES = ("README.md", "index.html", "leaderboard_data.json")


def load_prompt_templates(
    run: dict,
    prompt_dir: Path | None = None,
) -> list[dict[str, str]]:
    source_dir = PROMPT_TEMPLATE_DIR if prompt_dir is None else prompt_dir
    loaded = []
    for template_config in run.get("prompt_templates", ()):
        filename = template_config["filename"]
        path = source_dir / filename
        try:
            template = path.read_text(encoding="utf-8").rstrip()
        except OSError as error:
            raise ValueError(
                f"{run['model']} prompt template {filename} could not be read"
            ) from error
        if not template.strip():
            raise ValueError(
                f"{run['model']} prompt template {filename} is empty"
            )
        loaded.append(
            {"title": template_config["title"], "template": template}
        )
    if not loaded:
        raise ValueError(f"{run['model']} has no prompt templates configured")
    return loaded


def derive_full_run_cost(run: dict, metadata: dict, expected_samples: int) -> dict:
    source = run.get("cost_source", "unavailable")
    if source == "codex_api_equivalent":
        measurement = metadata.get("measured_cost")
        dataset = metadata.get("dataset")
        api_equivalent = (
            measurement.get("api_equivalent_usd")
            if isinstance(measurement, dict)
            else None
        )
        if (
            not isinstance(dataset, dict)
            or dataset.get("documents") != expected_samples
            or not isinstance(api_equivalent, (int, float))
        ):
            return {
                "full_run_cost_usd": None,
                "full_run_cost_source": "usage_unavailable",
                "full_run_cost_explanation": (
                    "Cost unavailable because the independent Codex cost measurement is "
                    "incomplete."
                ),
            }
        return {
            "full_run_cost_usd": float(api_equivalent),
            "full_run_cost_source": "codex_api_equivalent",
            "full_run_cost_explanation": (
                f"${api_equivalent:.2f} API-equivalent cost from the independent cost "
                "measurement; the leaderboard accuracy remains the released run."
            ),
        }
    if source == "claude_api_equivalent":
        samples = metadata.get("samples")
        if not isinstance(samples, dict) or len(samples) != expected_samples:
            return {
                "full_run_cost_usd": None,
                "full_run_cost_source": "usage_unavailable",
                "full_run_cost_explanation": (
                    "Cost unavailable because the released Claude metadata lacks a complete "
                    "per-document estimate set."
                ),
            }
        estimates = [sample.get("estimated_api_cost_usd") for sample in samples.values()]
        if any(not isinstance(value, (int, float)) for value in estimates):
            return {
                "full_run_cost_usd": None,
                "full_run_cost_source": "usage_unavailable",
                "full_run_cost_explanation": (
                    "Cost unavailable because the released Claude metadata lacks a complete "
                    "per-document estimate set."
                ),
            }
        return {
            "full_run_cost_usd": float(sum(estimates)),
            "full_run_cost_source": "claude_cli_estimate",
            "full_run_cost_explanation": (
                f"Sum of {expected_samples} Claude Code API-equivalent estimates; "
                "subscription billing may differ."
            ),
        }
    if source == "reducto_credits":
        credits = metadata.get("total_credits")
        if not isinstance(credits, (int, float)):
            return {
                "full_run_cost_usd": None,
                "full_run_cost_source": "usage_unavailable",
                "full_run_cost_explanation": (
                    "Cost unavailable because the released Reducto metadata does not include "
                    "total credits."
                ),
            }
        full_run_cost = float(credits) * REDUCTO_CREDIT_PRICE_USD
        leaderboard_override = run.get("leaderboard_cost_override_usd")
        if isinstance(leaderboard_override, (int, float)):
            experimental_cost = float(leaderboard_override)
            return {
                "full_run_cost_usd": experimental_cost,
                "full_run_cost_source": "reducto_leaderboard_override",
                "full_run_cost_explanation": (
                    f"Experimental leaderboard cost of ${experimental_cost:.2f}; current "
                    f"Reducto Standard list cost is ${full_run_cost:.2f}."
                ),
                "full_run_cost_beta": True,
                "full_run_cost_comparison": {
                    "current_credits": float(credits),
                    "current_cost_usd": full_run_cost,
                    "experimental_credits": round(
                        experimental_cost / REDUCTO_CREDIT_PRICE_USD
                    ),
                    "experimental_cost_usd": experimental_cost,
                },
            }
        return {
            "full_run_cost_usd": full_run_cost,
            "full_run_cost_source": "reducto_standard_list",
            "full_run_cost_explanation": (
                f"{credits:,.3f} credits × ${REDUCTO_CREDIT_PRICE_USD:.3f}/credit = "
                f"${full_run_cost:.2f} at Reducto's {PRICING_OBSERVED_DATE} Standard list rate; "
                "free or negotiated pricing may differ."
            ),
        }
    if source == "hosted_free":
        return {
            "full_run_cost_usd": 0.0,
            "full_run_cost_source": "together_free_hosted",
            "full_run_cost_explanation": (
                f"Together hosted this run on an endpoint advertised as free on "
                f"{PRICING_OBSERVED_DATE}; no dollar charge was recorded."
            ),
        }
    if source == "unavailable":
        return {
            "full_run_cost_usd": None,
            "full_run_cost_source": "usage_unavailable",
            "full_run_cost_explanation": (
                "Cost unavailable because this subscription run did not preserve token or "
                "dollar usage."
            ),
        }
    raise ValueError(f"Unsupported cost source: {source}")


def load_runs(results_dir: Path) -> tuple[list[dict], dict]:
    models = []
    dataset_meta: dict = {}
    expected_manifest: str | None = None
    expected_shape: tuple[int, int] | None = None
    for run in RUNS:
        run_dir = run["run_dir"]
        key = run["key"]
        report = json.loads((results_dir / run_dir / "evaluation_report.json").read_text(encoding="utf-8"))
        meta = json.loads((results_dir / run_dir / "run_metadata.json").read_text(encoding="utf-8"))
        stats = report["model_stats"][key]
        try:
            detailed_results = report["detailed_results"]
        except KeyError:
            raise ValueError(f"{run_dir} is missing detailed_results") from None
        document_samples = {detail["sample"] for detail in detailed_results}
        if (
            len(detailed_results) != stats["total_samples"]
            or len(document_samples) != stats["total_samples"]
        ):
            raise ValueError(
                f"{run_dir} expected {stats['total_samples']} unique documents, "
                f"found {len(detailed_results)} rows and {len(document_samples)} unique samples"
            )
        manifest = report["dataset"]["manifest_sha256"]
        shape = (stats["total_samples"], stats["total_rows"])
        if expected_manifest is None:
            expected_manifest = manifest
            expected_shape = shape
            dataset_meta = report["dataset"]
        elif manifest != expected_manifest or shape != expected_shape:
            raise ValueError(
                f"{run_dir} targets a different dataset: "
                f"manifest={manifest}, shape={shape}; "
                f"expected manifest={expected_manifest}, shape={expected_shape}"
            )
        cost_metadata = meta
        if cost_metadata_path := run.get("cost_metadata_path"):
            cost_metadata = json.loads(
                Path(cost_metadata_path).read_text(encoding="utf-8")
            )
        cost = derive_full_run_cost(run, cost_metadata, stats["total_samples"])
        models.append({
            "key": key,
            "harness": run["harness"],
            "model": run["model"],
            "protocol": run["protocol"],
            "prompt_templates": load_prompt_templates(run),
            "prompt_note": run["prompt_note"],
            **cost,
            "requested_model": run.get("requested_model", meta.get("requested_model", meta.get("model_id"))),
            "effort": run.get("effort", meta.get("effort", "default")),
            "cli_version": run.get(
                "cli_version",
                meta.get("cli_version_observed_at_metadata_write", meta.get("runner", "unknown")),
            ),
            "run_date": meta["generated_at"][:10],
            "stats": stats,
            "detailed_results": detailed_results,
        })
    return models, dataset_meta


def pct(value: float, digits: int = 1) -> str:
    return f"{100 * value:.{digits}f}"


def summarize_document_results(details: list[dict]) -> list[dict]:
    documents = []
    for detail in details:
        metrics = detail["metrics"]
        documents.append({
            "sample": detail["sample"],
            "tier": detail["tier"],
            "gold_records": metrics["ground_truth_count"],
            "predicted_records": metrics["predicted_count"],
            "exact_record_recall": metrics["exact_record_recall"],
            "field_f1": metrics["f1"],
            "complete_document": metrics["complete_document"],
        })
    return documents


def build_data(models: list[dict], dataset_meta: dict) -> dict:
    rows = []
    for m in models:
        s = m["stats"]
        roles = s["by_evaluation_role"]
        rows.append({
            "config": f"{m['harness']}, {m['model']} ({m['effort']})",
            "harness": m["harness"],
            "model": m["model"],
            "requested_model": m["requested_model"],
            "effort": m["effort"],
            "cli_version": m["cli_version"],
            "run_date": m["run_date"],
            "protocol": m["protocol"],
            "prompt_templates": m["prompt_templates"],
            "prompt_note": m["prompt_note"],
            "full_run_cost_usd": m["full_run_cost_usd"],
            "full_run_cost_source": m["full_run_cost_source"],
            "full_run_cost_explanation": m["full_run_cost_explanation"],
            "exact_record_recall": s["exact_record_recall"],
            "exact_record_precision": s["exact_record_precision"],
            "exact_record_f1": s["exact_record_f1"],
            "complete_documents": s["complete_documents"],
            "total_samples": s["total_samples"],
            "complete_document_rate": s["complete_document_rate"],
            "weighted_f1": s["weighted_f1"],
            "weighted_recall": s["weighted_recall"],
            "structural_exact_recall": roles["structural_challenge"]["exact_record_recall"],
            "scale_control_exact_recall": roles["scale_control"]["exact_record_recall"],
            "gold_records": s["total_rows"],
            "exact_record_matches": s["total_exact_record_matches"],
            "errors": s["errors"],
            "by_tier": s["by_tier"],
            "by_family": s["by_complexity_regime"],
            "by_stressor": s["by_stressor"],
            "documents": summarize_document_results(m["detailed_results"]),
        })
    rows.sort(
        key=lambda r: (r["complete_documents"], r["exact_record_recall"]),
        reverse=True,
    )
    return {
        "benchmark": "LongListBench",
        "version": RELEASE_VERSION,
        "dataset": dataset_meta,
        "protocol": (
            "All rows use the same dataset and scorer. Agentic CLI and Bonsai runs consume released "
            "OCR transcripts; Reducto Deep Extract runs on raw PDFs. Protocols are labeled separately."
        ),
        "results": rows,
    }


def format_full_run_cost(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:.2f}"


DISPLAYED_METRICS = {
    "full_run_cost_usd": ("min", lambda value: round(value, 2)),
    "exact_record_recall": ("max", lambda value: round(value * 100, 1)),
    "complete_documents": ("max", int),
    "structural_exact_recall": ("max", lambda value: round(value * 100, 1)),
    "scale_control_exact_recall": ("max", lambda value: round(value * 100, 1)),
    "weighted_f1": ("max", lambda value: round(value * 100, 1)),
}


def metric_leaders(results: list[dict]) -> dict[str, set[int]]:
    leaders: dict[str, set[int]] = {}
    for metric, (direction, display_value) in DISPLAYED_METRICS.items():
        candidates = [
            (index, display_value(row[metric]))
            for index, row in enumerate(results)
            if row.get(metric) is not None
        ]
        if not candidates:
            leaders[metric] = set()
            continue
        best_value = (
            min(value for _, value in candidates)
            if direction == "min"
            else max(value for _, value in candidates)
        )
        leaders[metric] = {
            index for index, value in candidates if value == best_value
        }
    return leaders


def render_prompt_templates(result: dict) -> str:
    templates = result.get("prompt_templates") or []
    if not templates:
        return ""
    note = html_module.escape(result.get("prompt_note", ""))
    blocks = "".join(
        "<section class='prompt-template'>"
        f"<strong>{html_module.escape(item['title'])}</strong>"
        "<div class='prompt-scroll'><pre><code>"
        f"{html_module.escape(item['template'])}"
        "</code></pre></div></section>"
        for item in templates
    )
    return (
        "<section class='prompt-panel'>"
        "<div class='prompt-panel-heading'><strong>Prompt template</strong>"
        f"<span>{note}</span></div>{blocks}</section>"
    )


def build_html(data: dict) -> str:
    results = data["results"]
    leaders = metric_leaders(results)
    rows_html = []
    for rank, result in enumerate(results, 1):
        result_index = rank - 1
        full_run_cost = result["full_run_cost_usd"]
        cost_label = format_full_run_cost(full_run_cost)
        cost_sort_value = "" if full_run_cost is None else full_run_cost
        cost_sort_missing = " data-sort-missing='true'" if full_run_cost is None else ""
        model_attribute = html_module.escape(result["model"], quote=True)
        cost_explanation = html_module.escape(
            result["full_run_cost_explanation"],
            quote=True,
        )
        cost_button = (
            '<button class="definition-button cost-definition-button" type="button" '
            f'aria-label="Explain full-run cost for {model_attribute}" '
            'aria-expanded="false" '
            f'data-metric-title="Full-run cost · {model_attribute}" '
            f'data-metric-definition="{cost_explanation}">i</button>'
        )

        def best_class(metric: str) -> str:
            return " metric-best" if result_index in leaders[metric] else ""

        documents = result.get("documents", [])
        prompt_templates_html = render_prompt_templates(result)
        has_details = bool(documents or prompt_templates_html)
        details_id = f"result-details-{rank}"
        details_button = (
            f'<button class="details-button" type="button" aria-expanded=\'false\' '
            f"aria-controls='{details_id}' data-model-name='{result['model']}' "
            f"aria-label='Show document details for {result['model']}'>"
            "<span data-details-label>Details</span>"
            "<span class='details-symbol' aria-hidden='true'>+</span></button>"
            if has_details
            else ""
        )
        document_rows = "".join(
            "<tr>"
            f"<td class='document-name'>{document['sample']}</td>"
            f"<td class='numeric'>{document['gold_records']}</td>"
            f"<td class='numeric'>{document['predicted_records']}</td>"
            f"<td class='numeric'>{pct(document['exact_record_recall'])}%</td>"
            f"<td class='numeric'>{pct(document['field_f1'])}%</td>"
            "<td class='document-complete'>"
            f"<span class='document-status {'complete' if document['complete_document'] else 'incomplete'}'>"
            f"{'Complete' if document['complete_document'] else 'Incomplete'}</span></td>"
            "</tr>"
            for document in documents
        )
        document_table_html = (
            "<div class='document-scroll'><table class='document-table'>"
            "<thead><tr><th>Document</th><th class='numeric'>Gold records</th>"
            "<th class='numeric'>Predicted</th><th class='numeric'>Exact recall</th>"
            "<th class='numeric'>Field F1</th><th>Complete</th></tr></thead>"
            f"<tbody>{document_rows}</tbody></table></div>"
            if documents
            else ""
        )
        rows_html.append(
            f"<tr data-result-row data-original-rank='{rank}' data-details-row='{details_id}'>"
            f"<td class='configuration' data-column='configuration' "
            f"data-sort-value='{result['model'].casefold()}'><div class='model-line'>"
            f"<strong>{result['model']}</strong></div>"
            f"<span>{result['harness']} · {result['effort']} · {result['run_date']}</span>"
            f"<div class='configuration-actions'><span class='protocol'>{result['protocol']}</span>"
            f"{details_button}</div></td>"
            f"<td class='numeric price{best_class('full_run_cost_usd')}' "
            "data-column='full_run_cost_usd' "
            f"data-sort-value='{cost_sort_value}'{cost_sort_missing}>"
            f"<span class='cost-cell'><span class='cost-value'>{cost_label}</span>"
            f"{cost_button}</span></td>"
            f"<td class='numeric{best_class('exact_record_recall')}' "
            "data-column='exact_record_recall' "
            f"data-sort-value='{result['exact_record_recall']}'>"
            f"{pct(result['exact_record_recall'])}%</td>"
            f"<td class='numeric{best_class('complete_documents')}' "
            "data-column='complete_documents' "
            f"data-sort-value='{result['complete_documents']}'>"
            f"{result['complete_documents']}/{result['total_samples']}</td>"
            f"<td class='numeric{best_class('structural_exact_recall')}' "
            "data-column='structural_exact_recall' "
            f"data-sort-value='{result['structural_exact_recall']}'>"
            f"{pct(result['structural_exact_recall'])}%</td>"
            f"<td class='numeric{best_class('scale_control_exact_recall')}' "
            "data-column='scale_control_exact_recall' "
            f"data-sort-value='{result['scale_control_exact_recall']}'>"
            f"{pct(result['scale_control_exact_recall'])}%</td>"
            f"<td class='numeric{best_class('weighted_f1')}' "
            "data-column='weighted_f1' "
            f"data-sort-value='{result['weighted_f1']}'>{pct(result['weighted_f1'])}%</td>"
            "</tr>"
            + (
                f"<tr class='detail-row' id='{details_id}' data-detail-for='{rank}' hidden>"
                "<td colspan='7'><div class='detail-panel'>"
                "<div class='detail-panel-heading'>"
                f"<strong>{result['model']}</strong><span>{len(documents)} documents</span></div>"
                f"{document_table_html}{prompt_templates_html}</div></td></tr>"
                if has_details
                else ""
            )
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<base target="_blank">
<title>LongListBench Leaderboard</title>
<style>
@font-face {{
  font-family: "Suisse Intl";
  src: local("Suisse Intl"), local("SuisseIntl-Regular");
  font-style: normal;
  font-weight: 400;
  font-display: swap;
}}
@font-face {{
  font-family: "Suisse Intl";
  src: local("Suisse Intl Medium"), local("SuisseIntl-Medium");
  font-style: normal;
  font-weight: 600;
  font-display: swap;
}}
:root {{
  --paper: #f9f7f3;
  --surface: #efede8;
  --surface-strong: #e8e5df;
  --ink: #363636;
  --muted: #77756f;
  --line: #d7d4cd;
  --signal: #ffe100;
  --signal-soft: #fff6ae;
  --black: #1d1d1b;
  --white: #ffffff;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: "Suisse Intl", "Helvetica Neue", Arial, sans-serif;
  font-size: 16px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}}
a {{ color: inherit; }}
a:focus-visible {{ outline: 3px solid var(--signal); outline-offset: 3px; }}
.shell {{
  width: min(1280px, calc(100% - 32px));
  margin: 0 auto;
}}
.leaderboard-section {{ padding-top: 12px; }}
.tablebox {{
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: 20px;
  background: rgba(255,255,255,.62);
}}
table {{ width: 100%; min-width: 1020px; border-collapse: collapse; font-size: 14px; }}
th, td {{
  padding: 18px 17px;
  border-top: 1px solid #e4e1db;
  text-align: left;
  white-space: nowrap;
}}
thead th {{
  border-top: 0;
  color: var(--muted);
  font: 10px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: .055em;
  text-transform: uppercase;
}}
.sort-button {{
  padding: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  letter-spacing: inherit;
  text-transform: inherit;
  white-space: nowrap;
}}
.column-actions {{
  display: flex;
  align-items: center;
  gap: 5px;
}}
th.numeric .column-actions {{ justify-content: flex-end; }}
.sort-button:hover, .sort-button:focus-visible {{ color: var(--ink); }}
.sort-button:focus-visible {{
  border-radius: 3px;
  outline: 3px solid var(--signal);
  outline-offset: 3px;
}}
.sort-arrow {{
  width: 11px;
  color: #aaa79f;
  font-size: 11px;
  text-align: center;
}}
th[aria-sort="ascending"] .sort-button,
th[aria-sort="descending"] .sort-button {{ color: var(--ink); }}
th[aria-sort="ascending"] .sort-arrow,
th[aria-sort="descending"] .sort-arrow {{ color: var(--ink); }}
.definition-button {{
  width: 16px;
  height: 16px;
  padding: 0;
  display: inline-grid;
  place-items: center;
  flex: 0 0 auto;
  border: 1px solid #c5c2bb;
  border-radius: 50%;
  background: rgba(255,255,255,.5);
  color: var(--muted);
  cursor: pointer;
  font: 9px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
  text-transform: lowercase;
}}
.definition-button:hover,
.definition-button[aria-expanded="true"] {{
  border-color: var(--ink);
  background: var(--ink);
  color: var(--white);
}}
.definition-button:focus-visible {{
  outline: 3px solid var(--signal);
  outline-offset: 2px;
}}
tbody > tr[data-result-row] {{ transition: background-color .16s ease; }}
tbody > tr[data-result-row]:hover {{ background: rgba(255,255,255,.68); }}
td.metric-best {{
  background: rgba(255,225,0,.16);
  font-weight: 600;
}}
tbody > tr[data-result-row]:hover > td.metric-best {{
  background: rgba(255,225,0,.24);
}}
.configuration {{ min-width: 270px; }}
.model-line {{ display: flex; align-items: center; gap: 8px; }}
.model-line strong {{ font-size: 15px; font-weight: 600; }}
.configuration > span:not(.protocol) {{
  display: block;
  margin-top: 2px;
  color: var(--muted);
  font-size: 11px;
}}
.configuration-actions {{
  margin-top: 7px;
  display: flex;
  align-items: center;
  gap: 7px;
}}
.protocol {{
  display: inline-block;
  padding: 3px 6px;
  border: 1px solid var(--line);
  border-radius: 4px;
  color: var(--muted);
  font: 9px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: .04em;
  text-transform: uppercase;
}}
.details-button {{
  padding: 3px 7px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid #bbb8b0;
  border-radius: 4px;
  background: rgba(255,255,255,.56);
  color: var(--ink);
  cursor: pointer;
  font: 9px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: .04em;
  text-transform: uppercase;
}}
.details-button:hover,
.details-button[aria-expanded="true"] {{
  border-color: var(--ink);
  background: var(--ink);
  color: var(--white);
}}
.details-button:focus-visible {{
  outline: 3px solid var(--signal);
  outline-offset: 2px;
}}
.details-symbol {{ width: 8px; text-align: center; }}
.detail-row[hidden] {{ display: none; }}
.detail-row > td {{
  padding: 0;
  border-top: 0;
  white-space: normal;
}}
.detail-panel {{
  padding: 14px 16px 16px;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  background: var(--surface-strong);
}}
.detail-panel-heading {{
  margin-bottom: 10px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}}
.detail-panel-heading strong {{ font-size: 13px; font-weight: 600; }}
.detail-panel-heading span {{
  color: var(--muted);
  font: 9px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: .04em;
  text-transform: uppercase;
}}
.document-scroll {{
  max-height: 380px;
  overflow: auto;
  border: 1px solid #cfccc4;
  border-radius: 10px;
  background: rgba(255,255,255,.72);
}}
.document-table {{
  width: 100%;
  min-width: 720px;
  border-collapse: collapse;
  font-size: 12px;
}}
.document-table th,
.document-table td {{
  padding: 9px 11px;
  border-top: 1px solid #e3e0d9;
  white-space: nowrap;
}}
.document-table thead th {{
  position: sticky;
  top: 0;
  z-index: 1;
  border-top: 0;
  background: #f1efea;
}}
.document-table tbody tr:hover {{ background: rgba(255,255,255,.8); }}
.document-name {{
  font: 10px/1.25 ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: .01em;
}}
.document-status {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font: 9px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: .03em;
  text-transform: uppercase;
}}
.document-status::before {{
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #b8b5ae;
}}
.document-status.complete {{ color: var(--ink); }}
.document-status.complete::before {{ background: var(--signal); }}
.prompt-panel {{
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}}
.prompt-panel-heading {{
  margin-bottom: 10px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}}
.prompt-panel-heading strong,
.prompt-template > strong {{
  font-size: 12px;
  font-weight: 600;
}}
.prompt-panel-heading span {{
  color: var(--muted);
  font-size: 11px;
}}
.prompt-template + .prompt-template {{ margin-top: 12px; }}
.prompt-scroll {{
  max-height: 320px;
  margin-top: 6px;
  overflow: auto;
  border: 1px solid #cfccc4;
  border-radius: 10px;
  background: rgba(255,255,255,.72);
}}
.prompt-scroll pre {{
  margin: 0;
  padding: 13px 14px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font: 11px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace;
}}
.numeric {{ text-align: right; font-variant-numeric: tabular-nums; }}
.price {{ font: 12px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace; }}
.cost-cell {{
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}}
.metric-popover {{
  position: fixed;
  z-index: 50;
  width: min(310px, calc(100vw - 24px));
  padding: 15px 16px 16px;
  border-radius: 12px;
  color: rgba(255,255,255,.74);
  background: var(--black);
  box-shadow: 0 16px 50px rgba(29,29,27,.24);
}}
.metric-popover[hidden] {{ display: none; }}
.metric-popover-label {{
  display: flex;
  align-items: center;
  gap: 7px;
  color: rgba(255,255,255,.5);
  font: 9px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: .06em;
  text-transform: uppercase;
}}
.metric-popover-label::before {{
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--signal);
}}
.metric-popover strong {{
  display: block;
  margin-top: 10px;
  color: var(--white);
  font-size: 15px;
  font-weight: 600;
}}
.metric-popover p {{
  margin: 5px 0 0;
  font-size: 12px;
  line-height: 1.5;
}}
.submit-panel {{
  margin: 56px 0 20px;
  padding: 24px 26px;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 32px;
  align-items: center;
  border-radius: 22px;
  background: var(--surface-strong);
}}
.submit-panel h2 {{
  margin: 0;
  font-size: clamp(30px, 3.5vw, 46px);
  font-weight: 400;
  letter-spacing: -.04em;
  line-height: 1;
}}
.submit-panel p {{ max-width: 720px; margin: 14px 0 0; color: var(--muted); font-size: 13px; }}
.submit-panel .button {{
  padding: 12px 16px;
  border-radius: 7px;
  background: var(--signal);
  color: #222;
  text-decoration: none;
  font-size: 13px;
  white-space: nowrap;
}}
.site-footer {{
  padding: 16px 0 28px;
  display: flex;
  justify-content: space-between;
  gap: 24px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 12px;
}}
.site-footer a {{ text-decoration-color: var(--signal); text-decoration-thickness: 3px; }}
@keyframes enter {{
  from {{ opacity: 0; transform: translateY(10px); }}
  to {{ opacity: 1; transform: none; }}
}}
@media (max-width: 820px) {{
  .shell {{ width: min(100% - 20px, 1280px); }}
  .submit-panel {{ margin-top: 48px; padding: 22px 18px; grid-template-columns: 1fr; }}
  .submit-panel .button {{ justify-self: start; }}
  .site-footer {{ flex-direction: column; }}
}}
@media (prefers-reduced-motion: reduce) {{
  html {{ scroll-behavior: auto; }}
  *, *::before, *::after {{ animation-duration: .01ms !important; animation-iteration-count: 1 !important; }}
}}
</style>
</head>
<body class="leaderboard-space">
<main class="shell">
  <section class="leaderboard-section" id="results">
    <div class="tablebox">
      <table data-sortable-table>
        <thead>
          <tr>
            <th aria-sort="none">
              <div class="column-actions">
                <button class="sort-button" type="button" data-sort-key="configuration"
                  data-sort-type="text" data-default-direction="ascending">
                  Configuration <span class="sort-arrow" aria-hidden="true">↕</span>
                </button>
              </div>
            </th>
            <th class="numeric" aria-sort="none">
              <div class="column-actions">
                <button class="sort-button" type="button" data-sort-key="full_run_cost_usd"
                  data-sort-type="number" data-default-direction="ascending">
                  Full-run cost <span class="sort-arrow" aria-hidden="true">↕</span>
                </button>
                <button class="definition-button" type="button" aria-label="Explain full-run cost"
                  aria-expanded="false" data-metric-title="Full-run cost"
                  data-metric-definition="Cost for all 32 documents using the best available run evidence; per-row hints explain each basis.">i</button>
              </div>
            </th>
            <th class="numeric" aria-sort="none">
              <div class="column-actions">
                <button class="sort-button" type="button" data-sort-key="exact_record_recall"
                  data-sort-type="number" data-default-direction="descending">
                  Exact recall <span class="sort-arrow" aria-hidden="true">↕</span>
                </button>
                <button class="definition-button" type="button" aria-label="Explain exact recall"
                  aria-expanded="false" data-metric-title="Exact recall"
                  data-metric-definition="Exact matched gold records divided by all gold records. Every normalized field in a record must match.">i</button>
              </div>
            </th>
            <th class="numeric" aria-sort="descending">
              <div class="column-actions">
                <button class="sort-button" type="button" data-sort-key="complete_documents"
                  data-sort-type="number" data-default-direction="descending">
                  Complete docs <span class="sort-arrow" aria-hidden="true">↓</span>
                </button>
                <button class="definition-button" type="button" aria-label="Explain complete documents"
                  aria-expanded="false" data-metric-title="Complete documents"
                  data-metric-definition="Documents where predicted and gold record multisets are identical, including duplicates and no extra records.">i</button>
              </div>
            </th>
            <th class="numeric" aria-sort="none">
              <div class="column-actions">
                <button class="sort-button" type="button" data-sort-key="structural_exact_recall"
                  data-sort-type="number" data-default-direction="descending">
                  Structural <span class="sort-arrow" aria-hidden="true">↕</span>
                </button>
                <button class="definition-button" type="button" aria-label="Explain structural recall"
                  aria-expanded="false" data-metric-title="Structural recall"
                  data-metric-definition="Exact-record recall on multisection, cross-page, multi-hop, and other structurally difficult document families.">i</button>
              </div>
            </th>
            <th class="numeric" aria-sort="none">
              <div class="column-actions">
                <button class="sort-button" type="button" data-sort-key="scale_control_exact_recall"
                  data-sort-type="number" data-default-direction="descending">
                  Scale ctrl <span class="sort-arrow" aria-hidden="true">↕</span>
                </button>
                <button class="definition-button" type="button" aria-label="Explain scale-control recall"
                  aria-expanded="false" data-metric-title="Scale-control recall"
                  data-metric-definition="Exact-record recall on dense schedules and returns that stress scale, OCR preservation, and output completeness.">i</button>
              </div>
            </th>
            <th class="numeric" aria-sort="none">
              <div class="column-actions">
                <button class="sort-button" type="button" data-sort-key="weighted_f1"
                  data-sort-type="number" data-default-direction="descending">
                  Field F1 <span class="sort-arrow" aria-hidden="true">↕</span>
                </button>
                <button class="definition-button" type="button" aria-label="Explain field F1"
                  aria-expanded="false" data-metric-title="Field F1"
                  data-metric-definition="F1 over matched flattened field-value pairs. A secondary partial-credit diagnostic for near misses.">i</button>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
    </div>
  </section>

  <section class="submit-panel" id="submit">
    <div>
      <h2>Submit a verified result</h2>
      <p>Run the reference evaluator, then open a repository issue or Space discussion with
      the evaluation report, run metadata, and per-sample predictions. Scores are reproduced
      before publication.</p>
    </div>
    <a class="button" href="https://github.com/kaydotai/longlistbench/issues">Submission details →</a>
  </section>

  <footer class="site-footer">
    <span>LongListBench {RELEASE_VERSION} · Open benchmark</span>
    <span>Full tier, family, and stressor slices in <a href="leaderboard_data.json">leaderboard_data.json</a></span>
  </footer>
</main>
<div class="metric-popover" id="metric-definition-popover" role="dialog"
  aria-modal="false" tabindex="-1" hidden>
  <span class="metric-popover-label">Metric definition</span>
  <strong></strong>
  <p></p>
</div>
<script>
(() => {{
  const table = document.querySelector("[data-sortable-table]");
  if (!table) return;
  const tbody = table.querySelector("tbody");
  const buttons = Array.from(table.querySelectorAll(".sort-button"));
  const definitionButtons = Array.from(table.querySelectorAll(".definition-button"));
  const detailButtons = Array.from(table.querySelectorAll(".details-button"));
  const popover = document.querySelector("#metric-definition-popover");
  const popoverTitle = popover.querySelector("strong");
  const popoverCopy = popover.querySelector("p");
  const collator = new Intl.Collator(undefined, {{ numeric: true, sensitivity: "base" }});
  let activeDefinitionButton = null;

  function closeDefinition() {{
    definitionButtons.forEach((button) => button.setAttribute("aria-expanded", "false"));
    popover.hidden = true;
    activeDefinitionButton = null;
  }}

  function setDetailsButton(button, expanded) {{
    button.setAttribute("aria-expanded", String(expanded));
    button.setAttribute(
      "aria-label",
      (expanded ? "Hide" : "Show") + " document details for " + button.dataset.modelName
    );
    button.querySelector("[data-details-label]").textContent = expanded ? "Hide" : "Details";
    button.querySelector(".details-symbol").textContent = expanded ? "−" : "+";
  }}

  function closeDetails() {{
    detailButtons.forEach((button) => {{
      const panel = document.getElementById(button.getAttribute("aria-controls"));
      panel.hidden = true;
      setDetailsButton(button, false);
    }});
  }}

  function toggleDetails(button) {{
    closeDefinition();
    const panel = document.getElementById(button.getAttribute("aria-controls"));
    const opening = panel.hidden;
    closeDetails();
    if (!opening) return;
    panel.hidden = false;
    setDetailsButton(button, true);
  }}

  function showDefinition(button) {{
    closeDetails();
    if (activeDefinitionButton === button && !popover.hidden) {{
      closeDefinition();
      return;
    }}
    closeDefinition();
    popoverTitle.textContent = button.dataset.metricTitle;
    popoverCopy.textContent = button.dataset.metricDefinition;
    popover.setAttribute("aria-label", button.dataset.metricTitle + " definition");
    popover.hidden = false;
    const anchor = button.getBoundingClientRect();
    const bounds = popover.getBoundingClientRect();
    const left = Math.min(
      window.innerWidth - bounds.width - 12,
      Math.max(12, anchor.right - bounds.width)
    );
    const below = anchor.bottom + 10;
    const top = below + bounds.height <= window.innerHeight - 12
      ? below
      : Math.max(12, anchor.top - bounds.height - 10);
    popover.style.left = left + "px";
    popover.style.top = top + "px";
    button.setAttribute("aria-expanded", "true");
    activeDefinitionButton = button;
    popover.focus({{ preventScroll: true }});
  }}

  function sortTable(button, direction) {{
    const key = button.dataset.sortKey;
    const type = button.dataset.sortType;
    const rows = Array.from(tbody.querySelectorAll("[data-result-row]"));
    closeDetails();
    rows.sort((leftRow, rightRow) => {{
      const leftCell = leftRow.querySelector('[data-column="' + key + '"]');
      const rightCell = rightRow.querySelector('[data-column="' + key + '"]');
      const left = leftCell.dataset.sortValue;
      const right = rightCell.dataset.sortValue;
      const leftMissing = leftCell.dataset.sortMissing === "true";
      const rightMissing = rightCell.dataset.sortMissing === "true";
      if (leftMissing !== rightMissing) return leftMissing ? 1 : -1;
      const comparison = type === "number"
        ? Number(left) - Number(right)
        : collator.compare(left, right);
      if (comparison === 0) {{
        return Number(leftRow.dataset.originalRank) - Number(rightRow.dataset.originalRank);
      }}
      return direction === "ascending" ? comparison : -comparison;
    }});
    rows.forEach((row) => {{
      tbody.appendChild(row);
      const detailRow = document.getElementById(row.dataset.detailsRow);
      if (detailRow) tbody.appendChild(detailRow);
    }});

    buttons.forEach((candidate) => {{
      const heading = candidate.closest("th");
      const active = candidate === button;
      heading.setAttribute("aria-sort", active ? direction : "none");
      candidate.querySelector(".sort-arrow").textContent = active
        ? (direction === "ascending" ? "↑" : "↓")
        : "↕";
    }});
  }}

  buttons.forEach((button) => {{
    button.addEventListener("click", () => {{
      const current = button.closest("th").getAttribute("aria-sort");
      const direction = current === "ascending"
        ? "descending"
        : current === "descending"
          ? "ascending"
          : button.dataset.defaultDirection;
      sortTable(button, direction);
    }});
  }});

  definitionButtons.forEach((button) => {{
    button.addEventListener("click", (event) => {{
      event.stopPropagation();
      showDefinition(button);
    }});
  }});

  detailButtons.forEach((button) => {{
    button.addEventListener("click", () => toggleDetails(button));
  }});

  document.addEventListener("click", (event) => {{
    if (!popover.hidden && !popover.contains(event.target)) closeDefinition();
  }});
  document.addEventListener("keydown", (event) => {{
    const expandedDetails = detailButtons.find(
      (button) => button.getAttribute("aria-expanded") === "true"
    );
    if (event.key === "Escape" && expandedDetails) {{
      closeDetails();
      expandedDetails.focus();
      return;
    }}
    if (event.key !== "Escape" || popover.hidden) return;
    const button = activeDefinitionButton;
    closeDefinition();
    button.focus();
  }});
  window.addEventListener("resize", closeDefinition);
  window.addEventListener("scroll", closeDefinition, true);
}})();
</script>
</body>
</html>
"""


README = f"""---
title: LongListBench Leaderboard
emoji: 📊
colorFrom: indigo
colorTo: blue
sdk: static
pinned: false
license: mit
short_description: Extraction results on LongListBench (32 PDFs, 29.6k records)
---

# LongListBench Leaderboard

Leaderboard for [LongListBench](https://huggingface.co/datasets/kaydotai/LongListBench) —
complete document-to-list extraction from long business PDFs.

## Submitting a result

1. Run your system on the dataset and score it with the
   [reference evaluator](https://github.com/kaydotai/longlistbench/blob/{RELEASE_VERSION}/benchmarks/evaluation_metrics.py).
2. Open a PR or issue on [GitHub](https://github.com/kaydotai/longlistbench) — or a discussion in
   this Space's Community tab — with your `evaluation_report.json`, `run_metadata.json`, and
   per-sample predictions.
3. Results are verified (scores must reproduce from the saved predictions) and added.

`leaderboard_data.json` holds the full numbers, including per-tier, per-family, and per-stressor slices.

This Space is generated by
[`benchmarks/export_leaderboard_space.py`](https://github.com/kaydotai/longlistbench/blob/main/benchmarks/export_leaderboard_space.py)
from the saved evaluation reports in the repository.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR, help="Directory holding run result folders.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory for the Space files.")
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID, help="Target Hugging Face Space repo ID.")
    parser.add_argument("--overwrite", action="store_true", help="Replace a non-empty output directory.")
    parser.add_argument("--upload", action="store_true", help="Upload the generated Space to Hugging Face Hub.")
    return parser.parse_args()


def prepare_output(output: Path, *, overwrite: bool) -> None:
    if output.is_file() or output.is_symlink():
        if not overwrite:
            raise FileExistsError(f"output path already exists: {output}; pass --overwrite to replace it")
        output.unlink()
    elif output.exists() and any(output.iterdir()):
        if not overwrite:
            raise FileExistsError(f"output directory is not empty: {output}; pass --overwrite to replace it")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)


def main() -> None:
    args = parse_args()
    models, dataset_meta = load_runs(args.results_dir)
    data = build_data(models, dataset_meta)
    prepare_output(args.output, overwrite=args.overwrite)
    (args.output / "leaderboard_data.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (args.output / "index.html").write_text(build_html(data), encoding="utf-8")
    (args.output / "README.md").write_text(README, encoding="utf-8")
    print(f"Wrote {args.output}")
    for path in sorted(args.output.iterdir()):
        print(f"  {path.name} ({path.stat().st_size} bytes)")
    if args.upload:
        from huggingface_hub import HfApi

        api = HfApi()
        api.create_repo(args.repo_id, repo_type="space", space_sdk="static", exist_ok=True)
        result = api.upload_folder(
            folder_path=str(args.output),
            repo_id=args.repo_id,
            repo_type="space",
            allow_patterns=list(SPACE_FILENAMES),
        )
        print(f"Uploaded: {result.commit_url}")


if __name__ == "__main__":
    main()
