import json
from pathlib import Path
from statistics import median

import pytest


ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_ROOT = ROOT / "benchmarks/cost_measurements"
MEASUREMENTS = {
    "gpt-5.5": MEASUREMENT_ROOT / "gpt55_20260729",
    "gpt-5.6-sol": MEASUREMENT_ROOT / "gpt56_sol_20260729",
}


def _credit_cost(payload: dict, usage: dict) -> float:
    rates = payload["pricing"]["chatgpt_credits_per_million_tokens"]
    uncached = usage["input_tokens"] - usage["cached_input_tokens"]
    return (
        uncached * rates["uncached_input"]
        + usage["cached_input_tokens"] * rates["cached_input"]
        + usage["output_tokens"] * rates["output"]
    ) / 1_000_000


@pytest.mark.parametrize(("model", "measurement_dir"), MEASUREMENTS.items())
def test_codex_cost_measurement_is_noncanonical_and_reconciles(
    model: str, measurement_dir: Path
) -> None:
    payload = json.loads(
        (measurement_dir / "usage_summary.json").read_text(encoding="utf-8")
    )

    assert payload["model"] == model
    assert payload["run_role"] == "cost_measurement"
    assert payload["canonical_result"] is False
    assert payload["dataset"]["documents"] == 32
    assert len(payload["per_document_usage"]) == 32
    assert len(payload["per_document_input_hashes"]) == 32
    assert payload["execution_protocol"] == {
        "worker_count": 4,
        "thread_scope": "one_ephemeral_thread_per_document",
        "repository_denied": True,
        "ground_truth_available_to_agent": False,
    }
    assert not list(measurement_dir.rglob("*predicted.json"))
    assert not list(measurement_dir.rglob("evaluation_report.*"))

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
        + totals["cache_write_input_tokens"] * (api_rates["cache_write_input"] or 0)
        + totals["output_tokens"] * api_rates["output"]
    ) / 1_000_000
    assert api_equivalent == pytest.approx(
        payload["measured_cost"]["api_equivalent_usd"]
    )


def test_gpt56_measurement_uses_fewer_tokens_and_credits_than_gpt55() -> None:
    payloads = {
        model: json.loads(
            (measurement_dir / "usage_summary.json").read_text(encoding="utf-8")
        )
        for model, measurement_dir in MEASUREMENTS.items()
    }
    gpt55 = payloads["gpt-5.5"]
    gpt56 = payloads["gpt-5.6-sol"]

    assert gpt55["dataset"] == gpt56["dataset"]
    assert gpt55["reasoning_effort"] == gpt56["reasoning_effort"] == "xhigh"
    assert (
        gpt55["pricing"]["chatgpt_credits_per_million_tokens"]
        == gpt56["pricing"]["chatgpt_credits_per_million_tokens"]
    )
    assert (
        gpt55["per_document_input_hashes"]
        == gpt56["per_document_input_hashes"]
    )

    for key in ("input_tokens", "output_tokens", "reasoning_output_tokens"):
        assert gpt56["measured_usage"][key] < gpt55["measured_usage"][key]
    assert (
        gpt56["measured_cost"]["chatgpt_credits"]
        < gpt55["measured_cost"]["chatgpt_credits"]
    )

    credit_ratio = (
        gpt56["measured_cost"]["chatgpt_credits"]
        / gpt55["measured_cost"]["chatgpt_credits"]
    )
    assert 1 - credit_ratio == pytest.approx(0.2306565717)

    paired_ratios = []
    cheaper_documents = 0
    for document_id, usage55 in gpt55["per_document_usage"].items():
        cost55 = _credit_cost(gpt55, usage55)
        cost56 = _credit_cost(gpt56, gpt56["per_document_usage"][document_id])
        paired_ratios.append(cost56 / cost55)
        cheaper_documents += cost56 < cost55

    assert cheaper_documents == 26
    assert median(paired_ratios) == pytest.approx(0.7686415416)
