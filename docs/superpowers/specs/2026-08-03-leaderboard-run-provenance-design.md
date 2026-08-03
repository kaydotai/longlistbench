# Leaderboard Run Provenance Design

## Goal

Make the published leaderboard identify the CLI version used for Codex and Claude results, keep GPT-5.6-Sol tied to its three new auditable runs, and explain why the new Sol aggregate differs from the paper's single-run result.

## Scope

- Keep GPT-5.6-Sol sourced from `benchmarks/cost_measurements/gpt56_sol_replicates_20260802/summary.json`, whose three entries reference the new `run_1`, `run_2`, and `run_3` result directories.
- Display a simple CLI label for Codex and Claude rows in both the leaderboard summary and the expanded Details header.
- Add a GPT-5.6-Sol-specific comparison note at the top of its expanded Details content.
- Regenerate the checked-in Space artifacts.

Provider/API labels such as Reducto API and Together API will not be added to the UI in this change.

## Data design

The exporter will continue to use each run's existing `cli_version` value. Display formatting will normalize the two supported forms:

- `codex-cli 0.146.0` becomes `Codex CLI v0.146.0`.
- `2.1.216 (Claude Code)` becomes `Claude Code v2.1.216`.

Other values will not be rendered as CLI versions. The Sol comparison note will be declared in the Sol run configuration and propagated into `leaderboard_data.json`, rather than being selected by model-name logic in the HTML renderer.

## UI design

For Codex and Claude rows, append the normalized CLI label to the existing metadata line. Repeat it in the expanded Details header so the version remains visible wherever the result context is shown.

At the beginning of GPT-5.6-Sol's Details content, before the per-document table, render a small neutral note with this meaning:

> The leaderboard averages three newer matched Sol runs made with Codex CLI v0.146.0, while the paper reports an older single-run baseline of 97.9%. Most of the difference comes from one large policy packet where the older run was unusually weak. Released transcripts and scoring targets match; a field-scope clarification affected three IFTA prompts but accounts for only a small part of the change. The run date and runtime also differ, so this is not a controlled model-improvement comparison.

The note should be concise, visually subordinate to the metrics, and absent from other rows.

## Verification

- Assert that the Sol leaderboard entry contains all three new result directories and reports `run_count: 3` with arithmetic-mean metrics.
- Assert that normalized Codex and Claude versions appear in the summary and Details markup, while Reducto and Together API labels do not.
- Assert that the paper-comparison note appears once, belongs to Sol, and precedes the document table.
- Regenerate `leaderboard_data.json` and `index.html` and run the leaderboard/export test suite.
- Open the local leaderboard and visually confirm the summary labels, Details header, and note placement.

## Alternatives considered

Hard-coding the note by model name would be smaller but makes content ownership implicit and brittle. Adding a new version column or badges would be more prominent than the requested simple metadata treatment. A structured per-run note plus inline metadata is the smallest approach that keeps the provenance explicit and maintainable.
