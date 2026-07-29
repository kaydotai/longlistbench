# Full-Run Cost and Metric Leaders Design

## Goal

Replace the leaderboard's blended token-price comparison with the comparable
cost of running the full 32-document LongListBench evaluation. Explain the
cost basis for every result, add both Reducto runs to the cost chart, and
replace the single overall leader treatment with cell-level highlights for the
best displayed value in each metric.

## Scope

This change affects the static leaderboard exporter, its generated
`leaderboard_data.json` and `index.html`, and exporter tests. It does not alter
saved predictions, evaluation reports, benchmark scores, or the ranking order.
It does not fabricate costs for runs whose usage was not preserved.

## Full-Run Cost Model

Each exported result will contain:

- `full_run_cost_usd`: numeric USD cost for all 32 documents, or `null`.
- `full_run_cost_explanation`: a run-specific explanation of the source,
  calculation, and limitations.
- `full_run_cost_source`: a short machine-readable cost provenance category.

The exporter will derive costs from saved metadata where possible:

| Result | Full-run cost | Calculation | Explanation requirements |
|---|---:|---|---|
| Claude Opus 4.8 | $44.86 | Sum all 32 `samples.*.estimated_api_cost_usd` values from `run_metadata.json`. | Claude Code API-equivalent estimate; the run used subscription authentication and this is not a billed subscription amount. |
| Claude Fable 5 | $102.84 | Sum all 32 `samples.*.estimated_api_cost_usd` values from `run_metadata.json`. | Same subscription and API-equivalent caveat as Opus. |
| Reducto Deep Extract v3, strict contract | $46.49 | `3,099.26794375 credits × $0.015/credit`. Credits come from `run_metadata.json`; the credit rate is the Reducto Standard list rate checked on 2026-07-28. | Nominal list-price equivalent; actual billing can be lower or zero under free credits or negotiated pricing. |
| Reducto Deep Extract v3, targeted prompt | $46.62 | `3,108.0628225 credits × $0.015/credit`. | Same list-price and billing caveat as the strict run. |
| Bonsai 27B | $0.00 | The released run used Together's hosted `Prism-ML/Ternary-Bonsai-27B` endpoint, advertised as free when checked on 2026-07-28. | Hosted free endpoint, not a local run; no dollar charge was recorded in the run metadata. |
| GPT-5.5 | n/a | No saved token or dollar usage. | Subscription run; insufficient saved usage to calculate a full-run cost. |
| GPT-5.6-Sol | n/a | No saved token or dollar usage. | Same missing-usage explanation as GPT-5.5. |

The static export must not fetch pricing from the network. The Reducto credit
rate and the Bonsai free-hosting statement will be explicit release constants
with their observation date. If a future Claude run has a partial set of
per-sample cost estimates, its full-run cost is unavailable rather than a
partial sum. If Reducto metadata lacks `total_credits`, its cost is likewise
unavailable.

## Table Design

The current `Token price` column becomes `Full-run cost`. Numeric values use
two decimal places, including `$0.00`; unavailable values display `n/a` and
sort after known values in either sort direction.

Every row receives a small accessible information button next to its cost.
The existing metric popover interaction will display that row's
`full_run_cost_explanation`. Every row-level explanation and the column-level
definition must be one concise sentence at most. The column definition will
state that the value covers all 32 documents and uses the best available cost
evidence for each run.

The table retains rank numbers and its default exact-recall ordering. It will
not declare an overall winner:

- Remove the `Leader` badge.
- Remove the winner-row background and accent border.
- Remove chart styling that designates a single leader.

Instead, highlight the best displayed value in each quantitative metric:

- Full-run cost: lowest known displayed cost; `n/a` is excluded.
- Exact recall: highest displayed percentage.
- Complete documents: highest displayed count.
- Structural recall: highest displayed percentage.
- Scale-control recall: highest displayed percentage.
- Field F1: highest displayed percentage.

Ties are determined at the precision shown to users: two decimal places for
USD costs, one decimal place for percentages, and exact integer counts for
complete documents. All displayed ties receive the same subtle highlighted
cell treatment. This prevents two visibly identical values from receiving
different styling because of hidden decimal precision. Rank and configuration
cells are never highlighted.

The highlight follows the supplied cell-coloring reference but uses the
leaderboard's existing palette: a quiet `--signal`-derived yellow fill on the
metric cell and `font-weight: 600` on its value. It introduces no badge, icon,
outline, new color token, or row-level background; hover may strengthen the
same fill slightly.

## Chart Design

The chart title becomes `Accuracy × full-run cost`. Its horizontal axis is
`Full-run cost (USD)` for the complete 32-document benchmark, while the
vertical axis remains exact-record recall.

The chart includes every result with a known numeric cost:

- Bonsai 27B
- Claude Opus 4.8
- Claude Fable 5
- Reducto strict contract
- Reducto targeted prompt

GPT-5.5 and GPT-5.6-Sol are excluded because their released artifacts lack
cost usage. The chart header explicitly reports `5 priced runs shown · 2 runs
omitted because cost usage is unavailable`.

The x-axis scale and ticks are derived from the largest known full-run cost,
rounded to a readable interval. Label offsets are defined for the two nearby
Reducto and Opus points so their labels do not overlap. Each SVG point includes
an accessible label with model, exact recall, full-run cost, and cost basis.
No point receives an overall-leader class.

## Data Flow and Interfaces

`load_runs()` continues to load the evaluation report and run metadata. A
focused cost-derivation helper consumes the run configuration and metadata and
returns the three cost fields. `build_data()` places those fields into each
public result and stops emitting the leaderboard's combined token-price value.

`build_html()` uses `full_run_cost_usd` for display and sorting, calls the
cell-leader helper before rendering rows, and emits per-row cost explanation
buttons. `build_cost_chart()` plots only numeric full-run costs and reports the
omitted count.

No saved result artifact is rewritten. The exporter remains a standalone
Python script with no new dependencies.

## Verification

Tests will cover:

- Complete Claude cost sums and rejection of partial per-sample cost data.
- Reducto credit conversion for both supplied credit totals.
- Bonsai's hosted-free explanation.
- GPT `null` costs and missing-last sorting markup.
- Presence of both Reducto points and absence of unknown-cost GPT points in
  the chart.
- Chart and table copy using `Full-run cost` rather than token price.
- Per-row explanation buttons for every result.
- Removal of the overall `Leader` badge and winner-row class.
- Cell highlighting for every metric, including displayed ties and exclusion
  of `n/a` values.

After unit tests pass, regenerate the static leaderboard, run the full test
suite, open the local page in the in-app browser, and verify:

- All seven rows render.
- Five cost-chart points render without overlapping labels.
- Both Reducto results appear in the chart at approximately $46.49 and $46.62.
- GPT costs show `n/a` with explanations.
- No overall leader treatment remains.
- Each metric's best displayed cell or tied cells are highlighted.
- Cost sorting keeps missing values last in both directions.
- The browser console has no errors.

## Delivery Constraint

Commit the implementation locally on `codex/add-reducto-results`. Do not push
the branch or create a remote pull request until the user explicitly
authorizes a push.
