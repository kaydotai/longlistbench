import json
from pathlib import Path, PureWindowsPath


RELEASE_RESULT_DIRS = (
    "claude_fable5_full_current_ocr_v2",
    "claude_opus48_full_current_ocr_v2",
    "codex_full_current_ocr_v2",
    "codex_gpt56_sol_full_current_ocr_v2",
    "codex_gpt56_sol_run1_current_ocr_v2",
    "codex_gpt56_sol_run2_current_ocr_v2",
    "codex_gpt56_sol_run3_current_ocr_v2",
    "codex_gpt56_terra_full_current_ocr_v2",
    "codex_gpt56_luna_full_current_ocr_v2",
)


def test_released_run_metadata_contains_only_portable_path_labels() -> None:
    for result_dir in RELEASE_RESULT_DIRS:
        metadata_path = Path("benchmarks/results") / result_dir / "run_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        denied_paths = metadata["additional_denied_paths"]

        assert denied_paths == ["<repo-parent>", "<user-home>/Desktop"]
        assert all(not Path(value).is_absolute() for value in denied_paths)
        assert all(not PureWindowsPath(value).is_absolute() for value in denied_paths)


def test_released_index_uses_portable_dataset_label() -> None:
    index = json.loads(Path("data/index.json").read_text(encoding="utf-8"))
    html = Path("data/index.html").read_text(encoding="utf-8")

    assert index["dataset_dir"] == "data"
    assert "/Users/" not in html
    assert "\\Users\\" not in html
