# Leaderboard variability hints

## Goal

Keep three-run arithmetic means visible in the leaderboard while moving sample-standard-deviation values out of the default presentation and into accessible hints. No visible leaderboard or per-document value should contain a plus/minus expression.

## Main leaderboard

- Terra and Luna continue to report arithmetic means across three matched full-corpus runs.
- Each metric cell displays only its mean: full-run cost, exact-record recall, complete documents, structural recall, scale-control recall, and Field F1.
- The configuration subtitle reads `n=3 · arithmetic mean`.
- Every aggregated metric cell exposes a small `i` button using the leaderboard's existing definition-popover behavior. Its hint identifies the value as a three-run arithmetic mean and reports the sample standard deviation with the metric's correct unit.
- The existing cost hint carries the cost standard deviation; no second cost button is added.
- Single-run rows retain their current values and interaction behavior.

## Per-document details

- Aggregated per-document Exact Recall and Field F1 display only their means.
- Each value has its own `i` hint containing `n=3` and its sample standard deviation.
- Predicted records continue to display the mean without a variability hint because the current exported document schema does not expose its standard deviation.
- Complete Runs remains a count such as `1/3`; it is not a plus/minus metric.

## Interaction and accessibility

- Reuse the existing clickable definition-button and popover implementation rather than browser-native title tooltips.
- Every new button has a metric-, model-, and document-specific accessible label where applicable.
- Keyboard focus, click-away dismissal, and Escape behavior remain controlled by the existing popover code.
- Hint text is HTML-escaped before insertion into data attributes.

## Data and output

- Mean and standard-deviation numbers remain unchanged in `leaderboard_data.json`.
- Sorting and best-value highlighting continue to use the mean.
- Only the generated HTML presentation changes; variability remains machine-readable and available on demand.

## Verification

- Add regression tests proving aggregated main cells and per-document cells render means without visible plus/minus text.
- Assert the corresponding hint metadata contains the correct sample standard deviation and run count.
- Assert the configuration subtitle no longer says `mean ± SD`.
- Preserve tests for single-run rows, sorting, highlighting, details, and popover interaction.
- Regenerate the static Space, run the complete test suite, and inspect the real local leaderboard.

## Out of scope

- Changing the three-run arithmetic-mean policy or underlying metrics.
- Adding confidence intervals, ranges, or individual-run values to hints.
- Redesigning the leaderboard layout or popover system.
