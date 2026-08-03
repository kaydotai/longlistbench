# Leaderboard Run Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the three-run Sol aggregate with simple Codex/Claude CLI version labels and an accurate paper-comparison note in Sol's Details panel.

**Architecture:** Keep run-specific provenance in the existing `RUNS` configuration, propagate it through the exporter data model, and keep HTML rendering generic. A small formatter recognizes only Codex CLI and Claude Code version strings; API-backed rows intentionally return no display label.

**Tech Stack:** Python 3, pytest, generated static HTML/CSS/JSON.

## Global Constraints

- GPT-5.6-Sol remains sourced from `benchmarks/cost_measurements/gpt56_sol_replicates_20260802/summary.json` and its three result directories.
- Render only Codex CLI and Claude Code versions; do not render Reducto API or Together API labels.
- Use the exact forms `Codex CLI v0.146.0` and `Claude Code v2.1.216` for current runs.
- Place the Sol-only paper comparison note before the per-document table.
- State that the paper used an older single run, the policy packet dominates the difference, three IFTA prompts had a limited field-scope clarification, and this is not a controlled model-improvement comparison.

---

## File map

- `benchmarks/export_leaderboard_space.py`: owns run provenance, exported data, version normalization, note markup, and note styling.
- `tests/test_export_leaderboard_space.py`: verifies the canonical Sol three-run sources and exported note metadata.
- `benchmarks/tests/test_leaderboard_export.py`: verifies version normalization and rendered summary/Details behavior.
- `dist/huggingface/leaderboard_space/index.html`: ignored local generated page used for browser verification.
- `dist/huggingface/leaderboard_space/leaderboard_data.json`: ignored local generated data used for provenance verification.

### Task 1: Export structured provenance and normalize CLI versions

**Files:**
- Modify: `tests/test_export_leaderboard_space.py`
- Modify: `benchmarks/tests/test_leaderboard_export.py`
- Modify: `benchmarks/export_leaderboard_space.py`

**Interfaces:**
- Consumes: existing `RUNS`, `load_runs(results_dir)`, and `build_data(models, dataset_meta)`.
- Produces: optional `detail_note: str | None` on model/result dictionaries and `format_cli_version(cli_version: str) -> str`.

- [ ] **Step 1: Write failing provenance and formatter tests**

Extend the Sol test with exact source and note assertions:

```python
assert sol["result_dirs"] == [
    "codex_gpt56_sol_run1_current_ocr_v2",
    "codex_gpt56_sol_run2_current_ocr_v2",
    "codex_gpt56_sol_run3_current_ocr_v2",
]
assert "older single-run baseline of 97.9%" in sol["detail_note"]
```

Build exported data in that test and assert the Sol result preserves the same `detail_note`. Add a parameterized formatter test covering:

```python
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("codex-cli 0.146.0", "Codex CLI v0.146.0"),
        ("2.1.216 (Claude Code)", "Claude Code v2.1.216"),
        ("Reducto API", ""),
        ("Together API", ""),
        ("unknown", ""),
    ],
)
def test_format_cli_version(raw: str, expected: str) -> None:
    assert export_leaderboard_space.format_cli_version(raw) == expected
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```bash
pytest -q tests/test_export_leaderboard_space.py::test_sol_leaderboard_entry_uses_three_run_mean_and_variability benchmarks/tests/test_leaderboard_export.py::test_format_cli_version
```

Expected: failure because `detail_note` and `format_cli_version` are not defined.

- [ ] **Step 3: Implement structured note propagation and version formatting**

Add a `SOL_PAPER_COMPARISON_NOTE` constant with the approved wording and attach it to the Sol `RUNS` entry as `"detail_note": SOL_PAPER_COMPARISON_NOTE`. In `load_runs`, copy `run.get("detail_note")` to each model. In `build_data`, copy `m.get("detail_note")` to each result.

Add this formatter near the existing display helpers:

```python
def format_cli_version(cli_version: str) -> str:
    if cli_version.startswith("codex-cli "):
        return f"Codex CLI v{cli_version.removeprefix('codex-cli ')}"
    if cli_version.endswith(" (Claude Code)"):
        version = cli_version.removesuffix(" (Claude Code)")
        return f"Claude Code v{version}"
    return ""
```

- [ ] **Step 4: Run focused tests and confirm they pass**

Run the command from Step 2. Expected: both tests pass.

- [ ] **Step 5: Commit structured provenance**

```bash
git add tests/test_export_leaderboard_space.py benchmarks/tests/test_leaderboard_export.py benchmarks/export_leaderboard_space.py
git commit -m "feat: add leaderboard run provenance metadata"
```

### Task 2: Render CLI versions and the Sol comparison note

**Files:**
- Modify: `benchmarks/tests/test_leaderboard_export.py`
- Modify: `benchmarks/export_leaderboard_space.py`

**Interfaces:**
- Consumes: `format_cli_version(cli_version: str) -> str` and optional result `detail_note` from Task 1.
- Produces: summary metadata and Details headers containing supported CLI versions, plus escaped `.result-note` markup before the document table.

- [ ] **Step 1: Write failing HTML tests**

Load real runs and build HTML. Assert each supported current label appears twice per matching row, API labels do not appear in metadata, and the Sol note precedes the first document table:

```python
models, dataset_meta = export_leaderboard_space.load_runs(
    export_leaderboard_space.RESULTS_DIR
)
data = export_leaderboard_space.build_data(models, dataset_meta)
html = export_leaderboard_space.build_html(data)

assert html.count("Codex CLI v0.146.0") == 6
assert html.count("Codex CLI v0.144.6") == 2
assert html.count("Claude Code v2.1.216") == 4
assert "Reducto API ·" not in html
assert "Together API ·" not in html
note_position = html.index("class='result-note'")
sol_table_position = html.index("class='document-table'", note_position)
assert note_position < sol_table_position
assert html.count("class='result-note'") == 1
assert "not a controlled model-improvement comparison" in html
```

- [ ] **Step 2: Run the HTML test and confirm failure**

Run:

```bash
pytest -q benchmarks/tests/test_leaderboard_export.py::test_cli_versions_and_sol_paper_note_render_in_details
```

Expected: failure because the labels and note markup are not rendered.

- [ ] **Step 3: Implement the minimal HTML and CSS changes**

In each `build_html` result loop, compute:

```python
cli_version_label = format_cli_version(result.get("cli_version", ""))
cli_version_metadata = f" · {cli_version_label}" if cli_version_label else ""
detail_note = result.get("detail_note")
detail_note_html = (
    f"<aside class='result-note'>{html_module.escape(detail_note)}</aside>"
    if detail_note
    else ""
)
```

Append `cli_version_metadata` after the harness in the summary metadata and after `n={run_count}` in the Details heading. Insert `detail_note_html` before `document_table_html`. Add restrained `.result-note` CSS using the existing `--line`, `--surface`, `--ink`, and `--muted` tokens.

- [ ] **Step 4: Run focused exporter tests**

Run:

```bash
pytest -q tests/test_export_leaderboard_space.py benchmarks/tests/test_leaderboard_export.py
```

Expected: all tests pass.

- [ ] **Step 5: Regenerate and inspect the local leaderboard**

Run:

```bash
python benchmarks/export_leaderboard_space.py --overwrite
```

Inspect `dist/huggingface/leaderboard_space/leaderboard_data.json` to confirm Sol has the exact three result directories, `run_count` is 3, `cli_version` is `codex-cli 0.146.0`, and `detail_note` is present. Open the existing local leaderboard at `http://127.0.0.1:8765/`, expand Sol Details, and verify the note and version placement at desktop and narrow viewport widths.

- [ ] **Step 6: Run the full test suite**

Run:

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit the rendered UI behavior**

```bash
git add benchmarks/tests/test_leaderboard_export.py benchmarks/export_leaderboard_space.py
git commit -m "feat: show leaderboard CLI provenance"
```
