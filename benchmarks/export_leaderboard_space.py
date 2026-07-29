#!/usr/bin/env python3
"""Build the static LongListBench leaderboard Space from saved evaluation reports."""

from __future__ import annotations

import argparse
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

RUNS = (
    {
        "run_dir": "codex_gpt56_sol_full_current_ocr_v2",
        "key": "codex_gpt56_sol",
        "harness": "Codex CLI",
        "model": "GPT-5.6-Sol",
        "protocol": "Agentic CLI",
        "cost_source": "unavailable",
    },
    {
        "run_dir": "claude_opus48_full_current_ocr_v2",
        "key": "claude_opus48",
        "harness": "Claude Code",
        "model": "Claude Opus 4.8",
        "protocol": "Agentic CLI",
        "cost_source": "claude_api_equivalent",
    },
    {
        "run_dir": "claude_fable5_full_current_ocr_v2",
        "key": "claude_fable5",
        "harness": "Claude Code",
        "model": "Claude Fable 5",
        "protocol": "Agentic CLI",
        "cost_source": "claude_api_equivalent",
    },
    {
        "run_dir": "codex_full_current_ocr_v2",
        "key": "codex_gpt55",
        "harness": "Codex CLI",
        "model": "GPT-5.5",
        "protocol": "Agentic CLI",
        "cost_source": "unavailable",
    },
    {
        "run_dir": "reducto_deep_extract_v3_targeted_prompt",
        "key": "reducto_deep_extract",
        "harness": "Reducto",
        "model": "Deep Extract v3 (targeted prompt)",
        "protocol": "Raw PDF · targeted prompt · 3,108 credits",
        "cost_source": "reducto_credits",
        "effort": "targeted fields",
        "requested_model": "v3",
        "cli_version": "Reducto API",
    },
    {
        "run_dir": "reducto_deep_extract_v3_strict_contract",
        "key": "reducto_deep_extract",
        "harness": "Reducto",
        "model": "Deep Extract v3 (strict contract)",
        "protocol": "Raw PDF · strict contract · 3,099 credits",
        "cost_source": "reducto_credits",
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
        "effort": "page pipeline",
        "requested_model": "Prism-ML/Ternary-Bonsai-27B",
        "cli_version": "Together API",
    },
)
SPACE_FILENAMES = ("README.md", "index.html", "leaderboard_data.json")


def derive_full_run_cost(run: dict, metadata: dict, expected_samples: int) -> dict:
    source = run.get("cost_source", "unavailable")
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
        cost = derive_full_run_cost(run, meta, stats["total_samples"])
        models.append({
            "key": key,
            "harness": run["harness"],
            "model": run["model"],
            "protocol": run["protocol"],
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


def combined_token_price(input_price: float | None, output_price: float | None) -> float | None:
    if input_price is None or output_price is None:
        return None
    return input_price + output_price


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
            "input_token_price": m["input_token_price"],
            "output_token_price": m["output_token_price"],
            "combined_token_price": combined_token_price(
                m["input_token_price"],
                m["output_token_price"],
            ),
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
    rows.sort(key=lambda r: r["exact_record_recall"], reverse=True)
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


def money(value: float) -> str:
    return f"${value:.0f}" if value.is_integer() else f"${value:g}"


def format_token_price(value: float | None) -> str:
    if value is None:
        return "n/a"
    return "$0 local" if value == 0 else f"{money(value)}/M"


def build_cost_chart(results: list[dict]) -> str:
    results = [row for row in results if row["combined_token_price"] is not None]
    width = 920
    height = 312
    left = 48
    right = 898
    top = 18
    bottom = 252
    plot_width = right - left
    plot_height = bottom - top
    max_price = max(60.0, *(row["combined_token_price"] for row in results))

    def x_pos(price: float) -> float:
        return left + (price / max_price) * plot_width

    def y_pos(score: float) -> float:
        return bottom - score * plot_height

    y_grid = []
    for percent in (0, 25, 50, 75, 100):
        y = y_pos(percent / 100)
        y_grid.append(
            f"<line x1='{left}' x2='{right}' y1='{y:.1f}' y2='{y:.1f}' class='grid-line'/>"
            f"<text x='{left - 8}' y='{y + 3:.1f}' text-anchor='end' class='axis-tick'>{percent}%</text>"
        )

    x_grid = []
    for value in (0, 15, 30, 45, 60):
        x = x_pos(value)
        x_grid.append(
            f"<line x1='{x:.1f}' x2='{x:.1f}' y1='{top}' y2='{bottom}' class='grid-line vertical'/>"
            f"<text x='{x:.1f}' y='{bottom + 19}' text-anchor='middle' class='axis-tick'>${value}</text>"
        )

    known_labels = {
        "GPT-5.6-Sol": (16, 24, "start"),
        "GPT-5.5": (16, 58, "start"),
        "Claude Opus 4.8": (-18, 26, "end"),
        "Claude Fable 5": (-14, 38, "end"),
        "Bonsai 27B": (18, -20, "start"),
    }
    point_html = []
    leader_model = max(results, key=lambda row: row["exact_record_recall"])["model"]
    for index, row in enumerate(results):
        x = x_pos(row["combined_token_price"])
        y = y_pos(row["exact_record_recall"])
        dx, dy, anchor = known_labels.get(
            row["model"],
            (16 if index % 2 == 0 else -16, 24 + index * 8, "start" if index % 2 == 0 else "end"),
        )
        label_x = x + dx
        label_y = y + dy
        combined = row["combined_token_price"]
        display_model = row["model"].removeprefix("Claude ")
        classes = ["point"]
        if row["model"] == leader_model:
            classes.append("leader")
        if combined == 0:
            classes.append("local")
        point_html.append(
            f"<g class='{' '.join(classes)}' data-model='{row['model']}'>"
            f"<line x1='{x:.1f}' y1='{y:.1f}' x2='{label_x:.1f}' y2='{label_y - 8:.1f}' class='label-line'/>"
            f"<circle cx='{x:.1f}' cy='{y:.1f}' r='6'/>"
            f"<text x='{label_x:.1f}' y='{label_y:.1f}' text-anchor='{anchor}' class='point-model'>{display_model}</text>"
            f"<text x='{label_x:.1f}' y='{label_y + 14:.1f}' text-anchor='{anchor}' class='point-meta'>"
            f"{pct(row['exact_record_recall'], 2)}%</text>"
            "</g>"
        )

    return (
        f"<svg class='cost-chart' viewBox='0 0 {width} {height}' role='img' "
        "aria-label='Exact-record recall versus blended token price per 1M tokens'>"
        f"{''.join(y_grid)}{''.join(x_grid)}"
        f"<line x1='{left}' x2='{right}' y1='{bottom}' y2='{bottom}' class='axis-line'/>"
        f"<text x='{(left + right) / 2:.1f}' y='{height - 14}' text-anchor='middle' class='axis-title'>"
        "Blended $ / 1M tokens</text>"
        f"<text x='8' y='{(top + bottom) / 2:.1f}' text-anchor='middle' class='axis-title' "
        f"transform='rotate(-90 8 {(top + bottom) / 2:.1f})'>"
        "EXACT-RECORD RECALL →</text>"
        f"{''.join(point_html)}"
        "</svg>"
    )


def build_html(data: dict) -> str:
    results = data["results"]
    rows_html = []
    for rank, result in enumerate(results, 1):
        combined = result["combined_token_price"]
        price_label = format_token_price(combined)
        price_sort_value = "" if combined is None else combined
        price_sort_missing = " data-sort-missing='true'" if combined is None else ""
        row_class = " class='winner'" if rank == 1 else ""
        leader_badge = "<span class='leader-badge'>Leader</span>" if rank == 1 else ""
        documents = result.get("documents", [])
        details_id = f"result-details-{rank}"
        details_button = (
            f'<button class="details-button" type="button" aria-expanded=\'false\' '
            f"aria-controls='{details_id}' data-model-name='{result['model']}' "
            f"aria-label='Show document details for {result['model']}'>"
            "<span data-details-label>Details</span>"
            "<span class='details-symbol' aria-hidden='true'>+</span></button>"
            if documents
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
        rows_html.append(
            f"<tr{row_class} data-result-row data-original-rank='{rank}' data-details-row='{details_id}'>"
            f"<td class='rank' data-rank-cell>#{rank}</td>"
            f"<td class='configuration' data-column='configuration' "
            f"data-sort-value='{result['model'].casefold()}'><div class='model-line'>"
            f"<strong>{result['model']}</strong>{leader_badge}</div>"
            f"<span>{result['harness']} · {result['effort']} · {result['run_date']}</span>"
            f"<div class='configuration-actions'><span class='protocol'>{result['protocol']}</span>"
            f"{details_button}</div></td>"
            f"<td class='numeric price' data-column='combined_token_price' "
            f"data-sort-value='{price_sort_value}'{price_sort_missing}>{price_label}</td>"
            f"<td class='numeric primary' data-column='exact_record_recall' "
            f"data-sort-value='{result['exact_record_recall']}'>"
            f"{pct(result['exact_record_recall'])}%</td>"
            f"<td class='numeric' data-column='complete_documents' "
            f"data-sort-value='{result['complete_documents']}'>"
            f"{result['complete_documents']}/{result['total_samples']}</td>"
            f"<td class='numeric' data-column='structural_exact_recall' "
            f"data-sort-value='{result['structural_exact_recall']}'>"
            f"{pct(result['structural_exact_recall'])}%</td>"
            f"<td class='numeric' data-column='scale_control_exact_recall' "
            f"data-sort-value='{result['scale_control_exact_recall']}'>"
            f"{pct(result['scale_control_exact_recall'])}%</td>"
            f"<td class='numeric' data-column='weighted_f1' "
            f"data-sort-value='{result['weighted_f1']}'>{pct(result['weighted_f1'])}%</td>"
            "</tr>"
            + (
                f"<tr class='detail-row' id='{details_id}' data-detail-for='{rank}' hidden>"
                "<td colspan='8'><div class='detail-panel'>"
                "<div class='detail-panel-heading'>"
                f"<strong>{result['model']}</strong><span>{len(documents)} documents</span></div>"
                "<div class='document-scroll'><table class='document-table'>"
                "<thead><tr><th>Document</th><th class='numeric'>Gold records</th>"
                "<th class='numeric'>Predicted</th><th class='numeric'>Exact recall</th>"
                "<th class='numeric'>Field F1</th><th>Complete</th></tr></thead>"
                f"<tbody>{document_rows}</tbody></table></div></div></td></tr>"
                if documents
                else ""
            )
        )

    chart_html = build_cost_chart(results)

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
.chart-section {{ padding-top: 12px; }}
.chart-card {{
  padding: 20px 22px 18px;
  border-radius: 26px;
  background: var(--surface);
}}
.chart-head {{
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 24px;
}}
.chart-head h3 {{
  margin: 0;
  font-size: 24px;
  font-weight: 400;
  letter-spacing: -.025em;
}}
.chart-head p {{ margin: 4px 0 0; color: var(--muted); font-size: 13px; }}
.chart-key {{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 7px;
  background: rgba(255,255,255,.58);
  color: var(--muted);
  font: 10px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: .03em;
  white-space: nowrap;
}}
.chart-key::before {{
  content: "";
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--signal);
}}
.chart-viewport {{ overflow-x: auto; overscroll-behavior-inline: contain; }}
.cost-chart {{
  width: 100%;
  height: auto;
  min-width: 900px;
  display: block;
  margin-top: 12px;
  overflow: visible;
}}
.grid-line {{ stroke: #d8d5ce; stroke-width: 1; }}
.grid-line.vertical {{ stroke-dasharray: 2 6; }}
.axis-line {{ stroke: #aaa69e; stroke-width: 1; }}
.axis-tick, .axis-title, .point-meta {{
  fill: #77756f;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}}
.axis-tick {{ font-size: 10px; }}
.axis-title {{ font-size: 9px; letter-spacing: .06em; }}
.point circle {{ fill: var(--ink); stroke: var(--surface); stroke-width: 3; }}
.point.leader circle {{ fill: var(--signal); stroke: var(--ink); stroke-width: 2.5; }}
.point.local circle {{ fill: var(--paper); stroke: var(--ink); }}
.label-line {{ stroke: #8c8982; stroke-width: 1; }}
.point-model {{ fill: var(--ink); font-size: 11px; font-weight: 600; }}
.point-meta {{ font-size: 8.5px; }}
.leaderboard-section {{ padding-top: 56px; }}
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
tbody > tr.winner {{
  background: linear-gradient(90deg, rgba(255,225,0,.22), rgba(255,225,0,.06) 46%, transparent);
}}
tbody > tr.winner:hover {{ background: linear-gradient(90deg, rgba(255,225,0,.3), rgba(255,225,0,.1) 46%, transparent); }}
tbody > tr.winner > td:first-child {{ box-shadow: inset 4px 0 0 var(--signal); }}
.rank {{
  width: 54px;
  color: var(--muted);
  font: 11px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
}}
.configuration {{ min-width: 270px; }}
.model-line {{ display: flex; align-items: center; gap: 8px; }}
.model-line strong {{ font-size: 15px; font-weight: 600; }}
.leader-badge {{
  padding: 3px 6px;
  border-radius: 4px;
  background: var(--signal);
  color: #292929;
  font: 9px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: .04em;
  text-transform: uppercase;
}}
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
.numeric {{ text-align: right; font-variant-numeric: tabular-nums; }}
.price {{ font: 12px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace; }}
.primary {{ font-size: 17px; font-weight: 600; }}
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
.chart-card {{ animation: enter .5s ease both; }}
@media (max-width: 820px) {{
  .shell {{ width: min(100% - 20px, 1280px); }}
  .chart-card {{ padding: 16px 12px 14px; border-radius: 20px; }}
  .chart-head {{ align-items: start; }}
  .chart-key {{ flex: 0 0 auto; }}
  .chart-viewport {{ margin-right: -16px; padding-right: 16px; }}
  .cost-chart {{ min-width: 760px; }}
  .leaderboard-section {{ padding-top: 48px; }}
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
  <section class="chart-section" aria-labelledby="cost-chart-title">
    <div class="chart-card">
      <div class="chart-head">
        <div>
          <h3 id="cost-chart-title">Accuracy × token price</h3>
          <p>Exact-record recall against blended list price per 1M tokens. Token-priced runs only.</p>
        </div>
        <div class="chart-key">Token-priced runs</div>
      </div>
      <div class="chart-viewport">{chart_html}</div>
    </div>
  </section>

  <section class="leaderboard-section" id="results">
    <div class="tablebox">
      <table data-sortable-table>
        <thead>
          <tr>
            <th>Rank</th>
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
                <button class="sort-button" type="button" data-sort-key="combined_token_price"
                  data-sort-type="number" data-default-direction="ascending">
                  Token price <span class="sort-arrow" aria-hidden="true">↕</span>
                </button>
                <button class="definition-button" type="button" aria-label="Explain token price"
                  aria-expanded="false" data-metric-title="Token price"
                  data-metric-definition="Blended input plus output list price per 1M tokens. Local excludes hardware and power; n/a indicates a non-token pricing model.">i</button>
              </div>
            </th>
            <th class="numeric" aria-sort="descending">
              <div class="column-actions">
                <button class="sort-button" type="button" data-sort-key="exact_record_recall"
                  data-sort-type="number" data-default-direction="descending">
                  Exact recall <span class="sort-arrow" aria-hidden="true">↓</span>
                </button>
                <button class="definition-button" type="button" aria-label="Explain exact recall"
                  aria-expanded="false" data-metric-title="Exact recall"
                  data-metric-definition="Exact matched gold records divided by all gold records. Every normalized field in a record must match.">i</button>
              </div>
            </th>
            <th class="numeric" aria-sort="none">
              <div class="column-actions">
                <button class="sort-button" type="button" data-sort-key="complete_documents"
                  data-sort-type="number" data-default-direction="descending">
                  Complete docs <span class="sort-arrow" aria-hidden="true">↕</span>
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
