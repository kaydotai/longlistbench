import json
from pathlib import Path
from types import SimpleNamespace

from benchmarks import run_codex_cli_evaluation as runner


def test_status_summary_fails_when_any_sample_fails() -> None:
    assert runner._all_statuses_succeeded([("a", 0), ("b", "skip"), ("c", "attest")])
    assert not runner._all_statuses_succeeded([])
    assert not runner._all_statuses_succeeded([("a", 0), ("b", "timeout")])
    assert not runner._all_statuses_succeeded([("a", "error: invalid JSON")])


def test_run_codex_uses_requested_model_and_effort(tmp_path, monkeypatch) -> None:
    (tmp_path / "prompt.md").write_text("extract", encoding="utf-8")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="ok")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    status, output = runner.run_codex(
        tmp_path,
        tmp_path / "repo",
        60,
        "gpt-5.6-sol",
        "xhigh",
    )

    assert status == 0
    assert output == "ok"
    assert "--json" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("-m") + 1] == "gpt-5.6-sol"
    assert 'model_reasoning_effort="xhigh"' in captured["cmd"]


def test_sandbox_profile_denies_additional_paths(tmp_path) -> None:
    repo = tmp_path / "repo"
    duplicate_data = tmp_path / "duplicate-data"

    profile = runner.sandbox_profile(repo, [duplicate_data])

    assert f'(subpath "{repo.resolve()}")' in profile
    assert f'(subpath "{duplicate_data.resolve()}")' in profile


def test_run_metadata_records_requested_codex_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runner, "_codex_cli_version", lambda: "codex-cli test")
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "sample_ocr_codex_gpt56_sol.log").write_text(
        """OpenAI Codex v0.144.4
model: gpt-5.6-sol
reasoning effort: xhigh
""",
        encoding="utf-8",
    )

    runner._write_run_metadata(
        repo_root=tmp_path / "kay" / "longlistbench",
        output_dir=tmp_path,
        transcript="ocr",
        model_key="codex_gpt56_sol",
        requested_model="gpt-5.6-sol",
        effort="xhigh",
        statuses=[("sample", 0)],
        extra_denied_paths=[tmp_path / "kay", tmp_path / "duplicate-data"],
    )

    payload = json.loads((tmp_path / runner.RUN_METADATA_FILE).read_text(encoding="utf-8"))
    assert payload["model_key"] == "codex_gpt56_sol"
    assert payload["requested_model"] == "gpt-5.6-sol"
    assert payload["effort"] == "xhigh"
    assert payload["additional_denied_paths"] == ["<repo-parent>", "<denied-path-2>"]
    assert str(tmp_path) not in json.dumps(payload)
    assert payload["sample_statuses"] == {"sample": 0}
    assert payload["samples"] == {
        "sample": {
            "cli_version": "v0.144.4",
            "observed_model": "gpt-5.6-sol",
            "observed_effort": "xhigh",
        }
    }


def test_codex_log_header_requires_model_and_effort() -> None:
    assert runner._parse_codex_log_header("OpenAI Codex v0.144.4\nmodel: gpt-5.6-sol\n") is None
    assert runner._cli_versions_match("v0.144.4", "codex-cli 0.144.4")
    assert not runner._cli_versions_match("v0.143.0", "codex-cli 0.144.4")


def test_codex_json_metadata_sums_completed_turn_usage() -> None:
    log = "\n".join(
        [
            '{"type":"thread.started","thread_id":"thread-123"}',
            "non-json diagnostic output",
            (
                '{"type":"turn.completed","usage":{"input_tokens":100,'
                '"cached_input_tokens":40,"cache_write_input_tokens":5,'
                '"output_tokens":12,"reasoning_output_tokens":7}}'
            ),
            (
                '{"type":"turn.completed","usage":{"input_tokens":80,'
                '"cached_input_tokens":30,"output_tokens":9,'
                '"reasoning_output_tokens":4}}'
            ),
        ]
    )

    metadata = runner._parse_codex_json_metadata(
        log,
        requested_model="gpt-5.6-sol",
        requested_effort="xhigh",
        runtime_version="codex-cli 0.145.0",
    )

    assert metadata == {
        "cli_version": "codex-cli 0.145.0",
        "observed_model": "gpt-5.6-sol",
        "observed_effort": "xhigh",
        "provenance_source": "codex_json_events_and_invocation",
        "completed_turn_count": 2,
        "usage": {
            "input_tokens": 180,
            "cached_input_tokens": 70,
            "cache_write_input_tokens": 5,
            "output_tokens": 21,
            "reasoning_output_tokens": 11,
        },
        "thread_id": "thread-123",
    }


def test_aggregate_codex_usage_counts_only_measured_samples() -> None:
    assert runner._aggregate_codex_usage(
        {
            "measured": {
                "usage": {
                    "input_tokens": 100,
                    "cached_input_tokens": 40,
                    "cache_write_input_tokens": 5,
                    "output_tokens": 12,
                    "reasoning_output_tokens": 7,
                }
            },
            "legacy": {"observed_model": "gpt-5.5"},
        }
    ) == {
        "measured_sample_count": 1,
        "input_tokens": 100,
        "cached_input_tokens": 40,
        "cache_write_input_tokens": 5,
        "output_tokens": 12,
        "reasoning_output_tokens": 7,
    }


def test_resume_requires_matching_input_and_prediction_hashes(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "document_ocr.md").write_text("transcript", encoding="utf-8")
    (workspace / "field_contract.md").write_text("contract", encoding="utf-8")
    (workspace / "prompt.md").write_text("prompt", encoding="utf-8")
    pred_path = tmp_path / "prediction.json"
    pred_path.write_text("[]", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")

    expected = runner._build_workspace_provenance(
        workspace=workspace,
        output_file=runner.OUTPUT_FILE_RECORDS,
        sample="sample",
        transcript="ocr",
        model_key="codex_gpt56_sol",
        requested_model="gpt-5.6-sol",
        effort="xhigh",
        dataset_manifest_path=manifest_path,
        runner_source_path=Path(__file__),
        runtime_version="codex-cli test",
    )
    metadata = runner._bind_prediction_provenance(expected, pred_path)

    assert runner._resume_metadata_matches(metadata, expected, pred_path)
    pred_path.write_text("[{}]", encoding="utf-8")
    assert not runner._resume_metadata_matches(metadata, expected, pred_path)

    pred_path.write_text("[]", encoding="utf-8")
    (workspace / "document_ocr.md").write_text("changed transcript", encoding="utf-8")
    changed = runner._build_workspace_provenance(
        workspace=workspace,
        output_file=runner.OUTPUT_FILE_RECORDS,
        sample="sample",
        transcript="ocr",
        model_key="codex_gpt56_sol",
        requested_model="gpt-5.6-sol",
        effort="xhigh",
        dataset_manifest_path=manifest_path,
        runner_source_path=Path(__file__),
        runtime_version="codex-cli test",
    )
    assert not runner._resume_metadata_matches(metadata, changed, pred_path)
