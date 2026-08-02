import pytest

from benchmarks import export_leaderboard_space


def test_terra_leaderboard_entry_uses_three_run_mean_and_variability() -> None:
    models, dataset = export_leaderboard_space.load_runs(
        export_leaderboard_space.RESULTS_DIR
    )
    terra = next(model for model in models if model["key"] == "codex_gpt56_terra")

    assert dataset["manifest_sha256"] == (
        "ccf1881c256e9b5a2f575e73061d6fd40cfe763dc446bc873fc63cedd0019133"
    )
    assert terra["requested_model"] == "gpt-5.6-terra"
    assert terra["effort"] == "xhigh"
    assert terra["run_count"] == 3
    assert terra["reporting_statistic"] == "arithmetic_mean"
    assert terra["stats"]["exact_record_recall"] == pytest.approx(
        0.9569917902631846
    )
    assert terra["stats"]["total_samples"] == 32
    assert terra["stats"]["complete_documents"] == 6
    assert terra["stats_standard_deviation"]["exact_record_recall"] == pytest.approx(
        0.02048238777731981
    )
    assert terra["full_run_cost_usd"] == pytest.approx(15.0115356)
    assert terra["full_run_cost_standard_deviation_usd"] == pytest.approx(
        0.41117905866364374
    )
    assert terra["full_run_cost_source"] == "codex_api_equivalent_mean"
    assert terra["full_run_cost_explanation"] == (
        "Mean API-equivalent cost across 3 saved full-corpus runs: "
        "$15.01 ± $0.41 sample SD."
    )


def test_luna_leaderboard_entry_uses_three_run_mean_and_variability() -> None:
    models, dataset = export_leaderboard_space.load_runs(
        export_leaderboard_space.RESULTS_DIR
    )
    luna = next(model for model in models if model["key"] == "codex_gpt56_luna")

    assert dataset["manifest_sha256"] == (
        "ccf1881c256e9b5a2f575e73061d6fd40cfe763dc446bc873fc63cedd0019133"
    )
    assert luna["requested_model"] == "gpt-5.6-luna"
    assert luna["effort"] == "xhigh"
    assert luna["run_count"] == 3
    assert luna["reporting_statistic"] == "arithmetic_mean"
    assert luna["stats"]["exact_record_recall"] == pytest.approx(
        0.9440634255661791
    )
    assert luna["stats"]["total_samples"] == 32
    assert luna["stats"]["complete_documents"] == 5
    assert luna["stats_standard_deviation"]["exact_record_recall"] == pytest.approx(
        0.03400791865033707
    )
    assert luna["full_run_cost_usd"] == pytest.approx(2.4144322933333333)
    assert luna["full_run_cost_standard_deviation_usd"] == pytest.approx(
        0.18390315648875805
    )
    assert luna["full_run_cost_source"] == "codex_api_equivalent_mean"
    assert luna["full_run_cost_explanation"] == (
        "Mean API-equivalent cost across 3 saved full-corpus runs: "
        "$2.41 ± $0.18 sample SD."
    )


def test_replicate_slices_and_documents_are_averaged() -> None:
    models, dataset = export_leaderboard_space.load_runs(
        export_leaderboard_space.RESULTS_DIR
    )
    data = export_leaderboard_space.build_data(models, dataset)
    luna = next(row for row in data["results"] if row["model"] == "GPT-5.6-Luna")
    sol = next(row for row in data["results"] if row["model"] == "GPT-5.6-Sol")

    assert luna["run_count"] == 3
    assert luna["structural_exact_recall"] == pytest.approx(
        0.8251723318279058
    )
    assert luna["by_stressor_standard_deviation"]["multi_column"][
        "exact_record_recall"
    ] > 0
    driver = next(
        document
        for document in luna["documents"]
        if document["sample"] == "driver_mvr_packet_001"
    )
    assert driver["exact_record_recall"] == pytest.approx(2 / 3)
    assert driver["complete_runs"] == 1
    assert driver["run_count"] == 3

    assert sol["run_count"] == 1
    assert sol["reporting_statistic"] == "single_run"
    assert sol["metric_standard_deviation"]["exact_record_recall"] == 0
