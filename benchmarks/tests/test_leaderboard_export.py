import json
from pathlib import Path
from unittest.mock import patch

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


def test_every_configured_run_has_non_empty_prompt_templates() -> None:
    for run in export_leaderboard_space.RUNS:
        templates = export_leaderboard_space.load_prompt_templates(run)
        assert templates
        assert all(set(template) == {"title", "template"} for template in templates)
        assert all(template["title"].strip() for template in templates)
        assert all(template["template"].strip() for template in templates)


def test_prompt_loader_rejects_missing_and_empty_files(tmp_path: Path) -> None:
    missing = {
        "model": "Missing",
        "prompt_templates": ({"title": "Task", "filename": "missing.txt"},),
    }
    with pytest.raises(ValueError, match="Missing.*missing.txt"):
        export_leaderboard_space.load_prompt_templates(missing, tmp_path)

    (tmp_path / "empty.txt").write_text(" \n", encoding="utf-8")
    empty = {
        "model": "Empty",
        "prompt_templates": ({"title": "Task", "filename": "empty.txt"},),
    }
    with pytest.raises(ValueError, match="Empty.*empty.txt.*empty"):
        export_leaderboard_space.load_prompt_templates(empty, tmp_path)


def test_load_runs_rejects_mixed_dataset_manifests(tmp_path: Path) -> None:
    runs = (
        {
            "run_dir": "run-a",
            "key": "model_a",
            "harness": "Harness A",
            "model": "Model A",
            "protocol": "Agentic CLI",
            "cost_source": "unavailable",
            "prompt_templates": export_leaderboard_space.AGENTIC_PROMPT_TEMPLATES,
            "prompt_note": "Test prompt condition.",
        },
        {
            "run_dir": "run-b",
            "key": "model_b",
            "harness": "Harness B",
            "model": "Model B",
            "protocol": "Agentic CLI",
            "cost_source": "unavailable",
            "prompt_templates": export_leaderboard_space.AGENTIC_PROMPT_TEMPLATES,
            "prompt_note": "Test prompt condition.",
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


def test_reducto_rows_disclose_primary_and_test_set_tuned_conditions() -> None:
    rows = {
        run["model"]: (run["protocol"], run["prompt_note"])
        for run in export_leaderboard_space.RUNS
        if run["harness"] == "Reducto"
    }

    assert rows == {
        "Deep Extract v3 (test-set tuned)": (
            "Raw PDF · test-set tuned",
            "Test-set tuned after observing benchmark failure modes.",
        ),
        "Deep Extract v3 (strict contract)": (
            "Raw PDF · strict contract",
            "Primary Reducto comparison condition.",
        ),
    }


def test_load_runs_bakes_prompt_templates_into_export_data() -> None:
    models, dataset_meta = export_leaderboard_space.load_runs(
        export_leaderboard_space.RESULTS_DIR
    )
    data = export_leaderboard_space.build_data(models, dataset_meta)

    assert all(result["prompt_templates"] for result in data["results"])
    tuned = next(
        result
        for result in data["results"]
        if result["model"] == "Deep Extract v3 (test-set tuned)"
    )
    strict = next(
        result
        for result in data["results"]
        if result["model"] == "Deep Extract v3 (strict contract)"
    )
    tuned_text = "\n".join(
        template["template"] for template in tuned["prompt_templates"]
    )
    strict_text = "\n".join(
        template["template"] for template in strict["prompt_templates"]
    )
    assert "Field granularity and fidelity:" in tuned_text
    assert "Identifier and label fields:" in tuned_text
    assert "Field granularity and fidelity:" not in strict_text
    assert strict["prompt_note"] == "Primary Reducto comparison condition."


def test_agentic_prompt_panel_distinguishes_task_prompt_from_contract_input() -> None:
    run = next(
        run
        for run in export_leaderboard_space.RUNS
        if run["model"] == "GPT-5.6-Sol"
    )

    html = export_leaderboard_space.render_prompt_templates(
        {
            "prompt_note": run["prompt_note"],
            "prompt_templates": export_leaderboard_space.load_prompt_templates(run),
        }
    )

    assert "Task prompt — exact" in html
    assert "Field contract template — separate per-document input" in html
    assert "claim samples received the published incident JSON Schema" in html
    assert "Agent task prompt" not in html


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


def test_sol_row_uses_api_equivalent_cost_from_independent_measurement() -> None:
    models, dataset_meta = export_leaderboard_space.load_runs(
        export_leaderboard_space.RESULTS_DIR
    )
    sol = next(model for model in models if model["model"] == "GPT-5.6-Sol")

    assert sol["full_run_cost_usd"] == pytest.approx(33.460299)
    assert sol["full_run_cost_source"] == "codex_api_equivalent"
    assert "independent cost measurement" in sol["full_run_cost_explanation"]

    html = export_leaderboard_space.build_html(
        export_leaderboard_space.build_data(models, dataset_meta)
    )
    assert "<span class='cost-value'>$33.46</span>" in html


def test_build_data_sorts_complete_documents_then_exact_recall_descending() -> None:
    def model(name: str, *, complete: int, exact: float) -> dict:
        return {
            "harness": "Test harness",
            "model": name,
            "requested_model": name,
            "effort": "xhigh",
            "cli_version": "test-cli",
                "run_date": "2026-07-28",
                "protocol": "Agentic CLI",
                "prompt_templates": [
                    {"title": "Agent task prompt", "template": "Extract records."}
                ],
                "prompt_note": "Test prompt condition.",
                "full_run_cost_usd": None,
            "full_run_cost_source": "usage_unavailable",
            "full_run_cost_explanation": "Usage unavailable.",
            "stats": {
                "exact_record_recall": exact,
                "exact_record_precision": exact,
                "exact_record_f1": exact,
                "complete_documents": complete,
                "total_samples": 32,
                "complete_document_rate": complete / 32,
                "weighted_f1": exact,
                "weighted_recall": exact,
                "by_evaluation_role": {
                    "structural_challenge": {"exact_record_recall": exact},
                    "scale_control": {"exact_record_recall": exact},
                },
                "total_rows": 100,
                "total_exact_record_matches": round(exact * 100),
                "errors": [],
                "by_tier": {},
                "by_complexity_regime": {},
                "by_stressor": {},
            },
            "detailed_results": [],
        }

    data = export_leaderboard_space.build_data(
        [
            model("few-complete-high-recall", complete=8, exact=0.99),
            model("tie-low-recall", complete=16, exact=0.89),
            model("tie-high-recall", complete=16, exact=0.96),
        ],
        {"total_samples": 32},
    )

    assert [result["model"] for result in data["results"]] == [
        "tie-high-recall",
        "tie-low-recall",
        "few-complete-high-recall",
    ]


def test_formats_full_run_cost_in_usd() -> None:
    assert export_leaderboard_space.format_full_run_cost(44.86076025) == "$44.86"
    assert export_leaderboard_space.format_full_run_cost(0.0) == "$0.00"
    assert export_leaderboard_space.format_full_run_cost(None) == "n/a"


def test_metric_leaders_include_all_ties_at_displayed_precision() -> None:
    results = [
        {
            "full_run_cost_usd": 44.864,
            "exact_record_recall": 0.99414,
            "complete_documents": 16,
            "structural_exact_recall": 0.9384,
            "scale_control_exact_recall": 0.9951,
            "weighted_f1": 0.994157,
        },
        {
            "full_run_cost_usd": 44.863,
            "exact_record_recall": 0.99381,
            "complete_documents": 16,
            "structural_exact_recall": 0.9380,
            "scale_control_exact_recall": 1.0,
            "weighted_f1": 0.99381,
        },
        {
            "full_run_cost_usd": None,
            "exact_record_recall": 0.9598,
            "complete_documents": 15,
            "structural_exact_recall": 0.859,
            "scale_control_exact_recall": 1.0,
            "weighted_f1": 0.9879,
        },
    ]

    assert export_leaderboard_space.metric_leaders(results) == {
        "full_run_cost_usd": {0, 1},
        "exact_record_recall": {0, 1},
        "complete_documents": {0, 1},
        "structural_exact_recall": {0, 1},
        "scale_control_exact_recall": {1, 2},
        "weighted_f1": {0, 1},
    }


def test_unpriced_table_cells_are_marked_as_missing_sort_values() -> None:
    data = {
        "results": [
            {
                "model": "GPT-5.6-Sol",
                "harness": "Codex CLI",
                "effort": "xhigh",
                "run_date": "2026-07-21",
                "protocol": "Agentic CLI",
                "full_run_cost_usd": None,
                "full_run_cost_source": "usage_unavailable",
                "full_run_cost_explanation": (
                    "Cost unavailable because this run did not preserve dollar usage."
                ),
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
                "full_run_cost_usd": 46.62,
                "full_run_cost_source": "reducto_standard_list",
                "full_run_cost_explanation": (
                    "Credits converted at Reducto's Standard list rate."
                ),
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
        "data-column='full_run_cost_usd' data-sort-value='' "
        "data-sort-missing='true'"
    ) in html
    assert "<span class='cost-value'>n/a</span>" in html
    assert html.count('class="definition-button cost-definition-button"') == 2
    assert 'aria-label="Explain full-run cost for GPT-5.6-Sol"' in html


def test_table_highlights_metric_leaders_without_an_overall_leader() -> None:
    def result(
        model: str,
        *,
        exact: float,
        cost: float | None,
        complete: int,
        structural: float,
        scale: float,
        field_f1: float,
    ) -> dict:
        return {
            "model": model,
            "harness": "Test harness",
            "effort": "xhigh",
            "run_date": "2026-07-26",
            "protocol": "Agentic CLI",
            "full_run_cost_usd": cost,
            "full_run_cost_source": "test",
            "full_run_cost_explanation": f"Recorded full-run cost for {model}.",
            "exact_record_recall": exact,
            "complete_documents": complete,
            "total_samples": 32,
            "structural_exact_recall": structural,
            "scale_control_exact_recall": scale,
            "weighted_f1": field_f1,
            "documents": [],
        }

    data = {
        "results": [
            result(
                "Model A",
                exact=0.99414,
                cost=44.864,
                complete=16,
                structural=0.9384,
                scale=0.9951,
                field_f1=0.994157,
            ),
            result(
                "Model B",
                exact=0.99381,
                cost=44.863,
                complete=16,
                structural=0.9380,
                scale=1.0,
                field_f1=0.99381,
            ),
            result(
                "Model C",
                exact=0.9598,
                cost=None,
                complete=15,
                structural=0.859,
                scale=1.0,
                field_f1=0.9879,
            ),
        ]
    }

    html = export_leaderboard_space.build_html(data)

    assert html.count(" metric-best'") == 12
    assert "td.metric-best {" in html
    assert "background: rgba(255,225,0,.16);" in html
    assert "background: rgba(255,225,0,.24);" in html
    assert "linear-gradient" not in html
    assert ">Leader</span>" not in html
    assert "leader-badge" not in html
    assert "tr.winner" not in html
    assert "point leader" not in html


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


def test_prompt_templates_render_below_document_table_and_are_escaped() -> None:
    result = {
        "model": "Prompt Model",
        "harness": "Test harness",
        "effort": "xhigh",
        "run_date": "2026-07-29",
        "protocol": "Agentic CLI",
        "full_run_cost_usd": None,
        "full_run_cost_source": "usage_unavailable",
        "full_run_cost_explanation": "Usage unavailable.",
        "exact_record_recall": 1.0,
        "complete_documents": 1,
        "total_samples": 1,
        "structural_exact_recall": 1.0,
        "scale_control_exact_recall": 1.0,
        "weighted_f1": 1.0,
        "prompt_note": "Historical <condition>.",
        "prompt_templates": [
            {
                "title": "Agent <task>",
                "template": (
                    "Read {{FIELD_CONTRACT}}.\n"
                    "Never emit <script>alert(1)</script>."
                ),
            }
        ],
        "documents": [
            {
                "sample": "sample-a",
                "gold_records": 1,
                "predicted_records": 1,
                "exact_record_recall": 1.0,
                "field_f1": 1.0,
                "complete_document": True,
            }
        ],
    }

    html = export_leaderboard_space.build_html({"results": [result]})

    assert html.index("class='document-table'") < html.index("class='prompt-panel'")
    assert "Historical &lt;condition&gt;." in html
    assert "Agent &lt;task&gt;" in html
    assert (
        "Read {{FIELD_CONTRACT}}.\n"
        "Never emit &lt;script&gt;alert(1)&lt;/script&gt;."
    ) in html
    assert "<script>alert(1)</script>" not in html
    assert "class='prompt-scroll'" in html


def test_build_html_starts_with_results_table_and_has_no_cost_chart() -> None:
    def result(
        model: str,
        *,
        exact: float,
        cost: float | None,
        protocol: str = "Agentic CLI",
    ) -> dict:
        return {
            "model": model,
            "harness": "Test harness",
            "effort": "xhigh",
            "run_date": "2026-07-26",
            "protocol": protocol,
            "prompt_note": (
                "Repository-denied agentic run over released OCR transcripts."
            ),
            "prompt_templates": [
                {
                    "title": "Agent task prompt",
                    "template": "Extract {{DOCUMENT_OCR}}.",
                }
            ],
            "full_run_cost_usd": cost,
            "full_run_cost_source": "test" if cost is not None else "usage_unavailable",
            "full_run_cost_explanation": (
                f"Recorded full-run cost for {model}."
                if cost is not None
                else "Cost unavailable because usage was not preserved."
            ),
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
            result("GPT-5.6-Sol", exact=0.9788, cost=None),
            result("Bonsai 27B", exact=0.1674, cost=0, protocol="Page pipeline"),
        ],
    }

    html = export_leaderboard_space.build_html(data)

    assert '<body class="leaderboard-space">' in html
    assert "<title>LongListBench Leaderboard</title>" in html
    assert '<main class="shell">\n  <section class="leaderboard-section"' in html
    assert "<header" not in html
    assert 'class="overview"' not in html
    assert 'font-family: "Suisse Intl", "Helvetica Neue", Arial, sans-serif' in html
    assert "kay.ai" not in html.lower()
    assert "/ research" not in html.lower()
    assert ">kay<" not in html.lower()
    assert "Every row." not in html
    assert "Accuracy × full-run cost" not in html
    assert "Full-run cost (USD)</text>" not in html
    assert "priced run shown" not in html
    assert ".leaderboard-section { padding-top: 12px; }" in html
    assert "INPUT + OUTPUT LIST PRICE" not in html
    assert "mobile-scroll-hint" not in html
    assert "cost-chart" not in html
    assert "GPT-5.6-Sol" in html
    assert "Bonsai 27B" in html
    assert "section-heading" not in html
    assert "Same dataset. Different protocol." not in html
    assert "Agentic CLI runs used repository-denied sandboxes." not in html
    assert 'data-sortable-table' in html
    assert 'data-sort-key="full_run_cost_usd"' in html
    assert 'data-sort-key="exact_record_recall"' in html
    assert (
        '<th class="numeric" aria-sort="descending">\n'
        '              <div class="column-actions">\n'
        '                <button class="sort-button" type="button" '
        'data-sort-key="complete_documents"'
    ) in html
    assert (
        'data-sort-key="complete_documents"\n'
        '                  data-sort-type="number" data-default-direction="descending">\n'
        '                  Complete docs <span class="sort-arrow" aria-hidden="true">↓</span>'
    ) in html
    assert "<th>Rank</th>" not in html
    assert "data-rank-cell" not in html
    assert "<td colspan='7'>" in html
    assert ".rank {" not in html
    assert html.count('class="details-button"') == 2
    assert html.count("class='detail-row'") == 2
    assert html.count("class='prompt-panel'") == 2
    assert html.count("Prompt template") == 2
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
    assert html.count('class="definition-button cost-definition-button"') == 2
    assert 'id="metric-definition-popover"' in html
    assert 'aria-label="Explain full-run cost"' in html
    assert 'aria-label="Explain field F1"' in html
    assert "function showDefinition(button) {\n    closeDetails();" in html
    assert "function toggleDetails(button) {\n    closeDefinition();" in html
