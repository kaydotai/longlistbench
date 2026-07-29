import json
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

import pytest

from benchmarks import export_leaderboard_space


def _write_run(
    results_dir: Path,
    run_dir: str,
    key: str,
    *,
    manifest: str,
    samples: int = 32,
    rows: int = 29_599,
) -> None:
    target = results_dir / run_dir
    target.mkdir(parents=True)
    report = {
        "dataset": {"manifest_sha256": manifest},
        "model_stats": {key: {"total_samples": samples, "total_rows": rows}},
        "detailed_results": [
            {
                "sample": f"sample_{index:03d}",
                "tier": "core_operations",
                "metrics": {
                    "ground_truth_count": 1,
                    "predicted_count": 1,
                    "exact_record_recall": 1.0,
                    "f1": 1.0,
                    "complete_document": True,
                },
            }
            for index in range(samples)
        ],
    }
    metadata = {
        "requested_model": key,
        "effort": "xhigh",
        "cli_version_observed_at_metadata_write": "test-cli",
        "generated_at": "2026-07-21T00:00:00+00:00",
    }
    (target / "evaluation_report.json").write_text(json.dumps(report), encoding="utf-8")
    (target / "run_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def test_load_runs_rejects_mixed_dataset_manifests(tmp_path: Path) -> None:
    runs = (
        {
            "run_dir": "run-a",
            "key": "model_a",
            "harness": "Harness A",
            "model": "Model A",
            "protocol": "Agentic CLI",
            "input_token_price": 1.0,
            "output_token_price": 2.0,
        },
        {
            "run_dir": "run-b",
            "key": "model_b",
            "harness": "Harness B",
            "model": "Model B",
            "protocol": "Agentic CLI",
            "input_token_price": 1.0,
            "output_token_price": 2.0,
        },
    )
    _write_run(tmp_path, "run-a", "model_a", manifest="a" * 64)
    _write_run(tmp_path, "run-b", "model_b", manifest="b" * 64)

    with patch.object(export_leaderboard_space, "RUNS", runs):
        with pytest.raises(ValueError, match="targets a different dataset"):
            export_leaderboard_space.load_runs(tmp_path)


def test_prepare_output_requires_explicit_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "space"
    output.mkdir()
    stale = output / "stale.txt"
    stale.write_text("stale", encoding="utf-8")

    with pytest.raises(FileExistsError, match="pass --overwrite"):
        export_leaderboard_space.prepare_output(output, overwrite=False)

    export_leaderboard_space.prepare_output(output, overwrite=True)
    assert output.is_dir()
    assert list(output.iterdir()) == []


def test_bonsai_run_is_labeled_local_and_together_ai(tmp_path: Path) -> None:
    bonsai_run = next(run for run in export_leaderboard_space.RUNS if run["model"] == "Bonsai 27B")
    _write_run(
        tmp_path,
        bonsai_run["run_dir"],
        bonsai_run["key"],
        manifest="a" * 64,
    )

    with patch.object(export_leaderboard_space, "RUNS", (bonsai_run,)):
        models, _ = export_leaderboard_space.load_runs(tmp_path)

    assert models[0]["harness"] == "Local + Together AI"


def test_derives_complete_claude_api_equivalent_cost() -> None:
    cost = export_leaderboard_space.derive_full_run_cost(
        {"cost_source": "claude_api_equivalent"},
        {
            "samples": {
                "sample-a": {"estimated_api_cost_usd": 1.25},
                "sample-b": {"estimated_api_cost_usd": 2.75},
            }
        },
        expected_samples=2,
    )

    assert cost == {
        "full_run_cost_usd": 4.0,
        "full_run_cost_source": "claude_cli_estimate",
        "full_run_cost_explanation": (
            "Sum of 2 Claude Code API-equivalent estimates; subscription billing may differ."
        ),
    }


def test_rejects_partial_claude_cost_metadata() -> None:
    cost = export_leaderboard_space.derive_full_run_cost(
        {"cost_source": "claude_api_equivalent"},
        {
            "samples": {
                "sample-a": {"estimated_api_cost_usd": 1.25},
                "sample-b": {},
            }
        },
        expected_samples=2,
    )

    assert cost["full_run_cost_usd"] is None
    assert cost["full_run_cost_source"] == "usage_unavailable"
    assert cost["full_run_cost_explanation"].count(". ") == 0


def test_converts_reducto_credits_at_standard_list_rate() -> None:
    cost = export_leaderboard_space.derive_full_run_cost(
        {"cost_source": "reducto_credits"},
        {"total_credits": 3108.0628225},
        expected_samples=32,
    )

    assert cost["full_run_cost_usd"] == pytest.approx(46.6209423375)
    assert cost["full_run_cost_source"] == "reducto_standard_list"
    assert "3,108.063 credits" in cost["full_run_cost_explanation"]
    assert "$0.015/credit" in cost["full_run_cost_explanation"]
    assert cost["full_run_cost_explanation"].count(". ") == 0


def test_marks_bonsai_as_free_hosted_run() -> None:
    cost = export_leaderboard_space.derive_full_run_cost(
        {"cost_source": "hosted_free"},
        {},
        expected_samples=32,
    )

    assert cost == {
        "full_run_cost_usd": 0.0,
        "full_run_cost_source": "together_free_hosted",
        "full_run_cost_explanation": (
            "Together hosted this run on an endpoint advertised as free on 2026-07-28; "
            "no dollar charge was recorded."
        ),
    }


def test_marks_subscription_run_without_usage_as_unavailable() -> None:
    cost = export_leaderboard_space.derive_full_run_cost(
        {"cost_source": "unavailable"},
        {},
        expected_samples=32,
    )

    assert cost == {
        "full_run_cost_usd": None,
        "full_run_cost_source": "usage_unavailable",
        "full_run_cost_explanation": (
            "Cost unavailable because this subscription run did not preserve token or dollar usage."
        ),
    }


def test_credit_pricing_does_not_become_a_zero_token_price() -> None:
    assert export_leaderboard_space.combined_token_price(None, None) is None
    assert export_leaderboard_space.format_token_price(None) == "n/a"


def test_cost_chart_omits_runs_without_token_pricing() -> None:
    chart = export_leaderboard_space.build_cost_chart(
        [
            {
                "model": "GPT-5.6-Sol",
                "combined_token_price": 35,
                "input_token_price": 5,
                "output_token_price": 30,
                "exact_record_recall": 0.9788,
            },
            {
                "model": "Reducto Deep Extract v3",
                "combined_token_price": None,
                "input_token_price": None,
                "output_token_price": None,
                "exact_record_recall": 0.9598,
            },
        ]
    )

    assert "GPT-5.6-Sol" in chart
    assert "Reducto Deep Extract v3" not in chart


def test_unpriced_table_cells_are_marked_as_missing_sort_values() -> None:
    data = {
        "results": [
            {
                "model": "GPT-5.6-Sol",
                "harness": "Codex CLI",
                "effort": "xhigh",
                "run_date": "2026-07-21",
                "protocol": "Agentic CLI",
                "combined_token_price": 35,
                "exact_record_recall": 0.9788,
                "complete_documents": 8,
                "total_samples": 32,
                "structural_exact_recall": 0.938,
                "scale_control_exact_recall": 0.995,
                "weighted_f1": 0.9938,
                "documents": [],
            },
            {
                "model": "Deep Extract v3",
                "harness": "Reducto",
                "effort": "targeted fields",
                "run_date": "2026-07-25",
                "protocol": "Raw PDF",
                "combined_token_price": None,
                "exact_record_recall": 0.9598,
                "complete_documents": 16,
                "total_samples": 32,
                "structural_exact_recall": 0.859,
                "scale_control_exact_recall": 1.0,
                "weighted_f1": 0.9879,
                "documents": [],
            }
        ]
    }

    html = export_leaderboard_space.build_html(data)

    assert (
        "data-column='combined_token_price' data-sort-value='' "
        "data-sort-missing='true'>n/a</td>"
    ) in html


@pytest.mark.parametrize(
    ("details", "message"),
    [
        (None, "missing detailed_results"),
        ([], "expected 32 unique documents"),
        (
            [
                {
                    "sample": "duplicate",
                    "tier": "core_operations",
                    "metrics": {},
                }
            ]
            * 32,
            "expected 32 unique documents",
        ),
    ],
)
def test_load_runs_requires_one_unique_document_result_per_sample(
    tmp_path: Path,
    details: list[dict] | None,
    message: str,
) -> None:
    run = export_leaderboard_space.RUNS[0]
    _write_run(tmp_path, run["run_dir"], run["key"], manifest="a" * 64)
    report_path = tmp_path / run["run_dir"] / "evaluation_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if details is None:
        del report["detailed_results"]
    else:
        report["detailed_results"] = details
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with patch.object(export_leaderboard_space, "RUNS", (run,)):
        with pytest.raises(ValueError, match=message):
            export_leaderboard_space.load_runs(tmp_path)


def test_summarize_document_results_keeps_only_comparable_metrics() -> None:
    details = [
        {
            "sample": "driver_mvr_packet_001",
            "tier": "core_operations",
            "metrics": {
                "ground_truth_count": 260,
                "predicted_count": 230,
                "exact_record_recall": 0.7153846154,
                "f1": 0.8687643899,
                "complete_document": False,
                "missing_ids": ["do-not-export"],
                "extra_ids": ["do-not-export"],
            },
        }
    ]

    assert export_leaderboard_space.summarize_document_results(details) == [
        {
            "sample": "driver_mvr_packet_001",
            "tier": "core_operations",
            "gold_records": 260,
            "predicted_records": 230,
            "exact_record_recall": 0.7153846154,
            "field_f1": 0.8687643899,
            "complete_document": False,
        }
    ]


def test_cost_chart_has_no_local_price_band() -> None:
    chart = export_leaderboard_space.build_cost_chart(
        [
            {
                "model": "Bonsai 27B",
                "combined_token_price": 0,
                "input_token_price": 0,
                "output_token_price": 0,
                "exact_record_recall": 0.1674,
            }
        ]
    )

    assert "local-band" not in chart


def test_cost_chart_uses_compact_points() -> None:
    chart = export_leaderboard_space.build_cost_chart(
        [
            {
                "model": "Bonsai 27B",
                "combined_token_price": 0,
                "input_token_price": 0,
                "output_token_price": 0,
                "exact_record_recall": 0.1674,
            }
        ]
    )

    assert "r='6'" in chart
    assert "r='9'" not in chart


def test_cost_chart_keeps_axis_margins_compact() -> None:
    chart = export_leaderboard_space.build_cost_chart(
        [
            {
                "model": "Bonsai 27B",
                "combined_token_price": 0,
                "input_token_price": 0,
                "output_token_price": 0,
                "exact_record_recall": 0.1674,
            }
        ]
    )
    svg = ElementTree.fromstring(chart)
    _, _, width, height = map(float, svg.attrib["viewBox"].split())
    baseline = next(element for element in svg if element.attrib.get("class") == "axis-line")
    x_axis_title = next(
        element for element in svg if element.text == "Blended $ / 1M tokens"
    )
    plot_left = float(baseline.attrib["x1"])
    plot_bottom = float(baseline.attrib["y1"])
    title_y = float(x_axis_title.attrib["y"])

    assert plot_left / width <= 0.065
    assert (title_y - plot_bottom) / height <= 0.15


def test_cost_chart_labels_are_compact_and_show_only_model_score() -> None:
    chart = export_leaderboard_space.build_cost_chart(
        [
            {
                "model": "GPT-5.6-Sol",
                "combined_token_price": 35,
                "input_token_price": 5,
                "output_token_price": 30,
                "exact_record_recall": 0.9788,
            },
            {
                "model": "Bonsai 27B",
                "combined_token_price": 0,
                "input_token_price": 0,
                "output_token_price": 0,
                "exact_record_recall": 0.1674,
            },
            {
                "model": "Claude Opus 4.8",
                "combined_token_price": 30,
                "input_token_price": 5,
                "output_token_price": 25,
                "exact_record_recall": 0.9771,
            },
        ]
    )

    assert "class='point-meta'>97.88%</text>" in chart
    assert "class='point-meta'>16.74%</text>" in chart
    assert "class='point-model'>Opus 4.8</text>" in chart
    assert "data-model='Claude Opus 4.8'" in chart
    assert "$35/M" not in chart
    assert "$0 token fee" not in chart


def test_build_html_starts_with_cost_chart_and_has_no_page_header() -> None:
    def result(
        model: str,
        *,
        exact: float,
        price: float,
        protocol: str = "Agentic CLI",
    ) -> dict:
        return {
            "model": model,
            "harness": "Test harness",
            "effort": "xhigh",
            "run_date": "2026-07-26",
            "protocol": protocol,
            "combined_token_price": price,
            "input_token_price": price / 6,
            "output_token_price": price * 5 / 6,
            "exact_record_recall": exact,
            "complete_documents": 1,
            "total_samples": 32,
            "structural_exact_recall": exact - 0.05,
            "scale_control_exact_recall": exact + 0.01,
            "weighted_f1": min(1, exact + 0.01),
            "documents": [
                {
                    "sample": "driver_mvr_packet_001",
                    "tier": "core_operations",
                    "gold_records": 260,
                    "predicted_records": 230,
                    "exact_record_recall": exact,
                    "field_f1": min(1, exact + 0.01),
                    "complete_document": False,
                }
            ],
        }

    data = {
        "benchmark": "LongListBench",
        "version": "v2.2.1",
        "dataset": {"total_samples": 32, "total_rows": 29_599},
        "protocol": "Mixed protocol",
        "results": [
            result("GPT-5.6-Sol", exact=0.9788, price=35),
            result("Bonsai 27B", exact=0.1674, price=0, protocol="Page pipeline"),
        ],
    }

    html = export_leaderboard_space.build_html(data)

    assert '<body class="leaderboard-space">' in html
    assert "<title>LongListBench Leaderboard</title>" in html
    assert '<main class="shell">\n  <section class="chart-section"' in html
    assert "<header" not in html
    assert 'class="overview"' not in html
    assert 'font-family: "Suisse Intl", "Helvetica Neue", Arial, sans-serif' in html
    assert "kay.ai" not in html.lower()
    assert "/ research" not in html.lower()
    assert ">kay<" not in html.lower()
    assert "Every row." not in html
    assert "Accuracy × token price" in html
    assert "Blended $ / 1M tokens</text>" in html
    assert "INPUT + OUTPUT LIST PRICE" not in html
    assert "mobile-scroll-hint" not in html
    assert "cost-chart" in html
    assert "GPT-5.6-Sol" in html
    assert "Bonsai 27B" in html
    assert "section-heading" not in html
    assert "Same dataset. Different protocol." not in html
    assert "Agentic CLI runs used repository-denied sandboxes." not in html
    assert 'data-sortable-table' in html
    assert 'data-sort-key="combined_token_price"' in html
    assert 'data-sort-key="exact_record_recall"' in html
    assert 'aria-sort="descending"' in html
    assert html.count('class="details-button"') == 2
    assert html.count("class='detail-row'") == 2
    assert "driver_mvr_packet_001" in html
    assert "Gold records" in html
    assert "Predicted" in html
    assert "Field F1" in html
    assert "aria-expanded='false'" in html
    assert " hidden>" in html
    assert 'tbody.querySelectorAll("[data-result-row]")' in html
    assert '<details class="metric-guide">' not in html
    assert "metric-grid" not in html
    assert html.count('class="definition-button"') == 6
    assert 'id="metric-definition-popover"' in html
    assert 'aria-label="Explain token price"' in html
    assert 'aria-label="Explain field F1"' in html
    assert "function showDefinition(button) {\n    closeDetails();" in html
    assert "function toggleDetails(button) {\n    closeDefinition();" in html
