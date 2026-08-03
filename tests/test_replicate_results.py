import json
from pathlib import Path

from benchmarks.check_replicate_summary import (
    DEFAULT_SUMMARIES,
    RESULTS_DIR,
    verify_summary,
)


def test_replicate_packages_and_summaries_are_consistent() -> None:
    for summary in DEFAULT_SUMMARIES:
        assert verify_summary(summary, replay_reports=False) == []


def test_replicated_models_use_the_same_transcripts_contracts_and_prompts() -> None:
    fingerprints = []
    for summary_path in DEFAULT_SUMMARIES:
        summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
        reference_dir = RESULTS_DIR / summary["runs"][0]["result_dir"]
        metadata = json.loads(
            (reference_dir / "run_metadata.json").read_text(encoding="utf-8")
        )
        fingerprints.append(
            {
                sample: tuple(
                    sample_metadata[key]
                    for key in (
                        "transcript_sha256",
                        "field_contract_sha256",
                        "prompt_sha256",
                    )
                )
                for sample, sample_metadata in metadata["samples"].items()
            }
        )

    assert all(value == fingerprints[0] for value in fingerprints[1:])
