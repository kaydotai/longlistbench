import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_DIR = ROOT / "benchmarks/cost_measurements/gpt56_sol_20260729"
USAGE_PATH = MEASUREMENT_DIR / "usage_summary.json"


def test_codex_cost_measurement_is_noncanonical_and_reconciles() -> None:
    payload = json.loads(USAGE_PATH.read_text(encoding="utf-8"))

    assert payload["run_role"] == "cost_measurement"
    assert payload["canonical_result"] is False
    assert payload["dataset"]["documents"] == 32
    assert len(payload["per_document_usage"]) == 32
    assert not list(MEASUREMENT_DIR.rglob("*predicted.json"))
    assert not list(MEASUREMENT_DIR.rglob("evaluation_report.*"))

    totals = payload["measured_usage"]
    for key in (
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    ):
        assert sum(
            usage[key] for usage in payload["per_document_usage"].values()
        ) == totals[key]
    assert totals["uncached_input_tokens"] == (
        totals["input_tokens"] - totals["cached_input_tokens"]
    )

    credit_rates = payload["pricing"]["chatgpt_credits_per_million_tokens"]
    credits = (
        totals["uncached_input_tokens"] * credit_rates["uncached_input"]
        + totals["cached_input_tokens"] * credit_rates["cached_input"]
        + totals["output_tokens"] * credit_rates["output"]
    ) / 1_000_000
    assert credits == pytest.approx(payload["measured_cost"]["chatgpt_credits"])

    api_rates = payload["pricing"]["api_usd_per_million_tokens"]
    api_equivalent = (
        totals["uncached_input_tokens"] * api_rates["uncached_input"]
        + totals["cached_input_tokens"] * api_rates["cached_input"]
        + totals["cache_write_input_tokens"] * api_rates["cache_write_input"]
        + totals["output_tokens"] * api_rates["output"]
    ) / 1_000_000
    assert api_equivalent == pytest.approx(
        payload["measured_cost"]["api_equivalent_usd"]
    )
