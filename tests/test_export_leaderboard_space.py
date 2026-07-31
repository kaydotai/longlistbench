from benchmarks import export_leaderboard_space


def test_terra_leaderboard_entry_uses_preselected_run_and_same_run_cost() -> None:
    models, dataset = export_leaderboard_space.load_runs(
        export_leaderboard_space.RESULTS_DIR
    )
    terra = next(model for model in models if model["key"] == "codex_gpt56_terra")

    assert dataset["manifest_sha256"] == (
        "ccf1881c256e9b5a2f575e73061d6fd40cfe763dc446bc873fc63cedd0019133"
    )
    assert terra["requested_model"] == "gpt-5.6-terra"
    assert terra["effort"] == "xhigh"
    assert terra["stats"]["exact_record_recall"] == 0.944930571978783
    assert terra["stats"]["total_samples"] == 32
    assert terra["stats"]["complete_documents"] == 5
    assert terra["full_run_cost_usd"] == 14.5439308
    assert terra["full_run_cost_source"] == "codex_api_equivalent"
    assert terra["full_run_cost_explanation"] == (
        "$14.54 API-equivalent cost derived from the same saved full-corpus run."
    )
