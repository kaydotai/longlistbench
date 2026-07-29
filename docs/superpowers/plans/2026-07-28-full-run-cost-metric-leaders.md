# Full-Run Cost and Metric Leaders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace token-price comparisons with provenance-aware full-run costs, add Reducto to the chart, and highlight the best displayed cells per metric without declaring an overall leader.

**Architecture:** The static exporter will derive a normalized cost record from each run's saved metadata, carry it through `leaderboard_data.json`, and render it in the table and SVG chart. A separate display-key helper will identify all visible ties per metric so styling is deterministic and testable.

**Tech Stack:** Python 3, pytest, static HTML/CSS/JavaScript, SVG, existing LongListBench result metadata.

## Global Constraints

- Cost explanations and the column definition are one concise sentence at most.
- Do not fabricate GPT-5.5 or GPT-5.6-Sol costs; display `n/a` and exclude them from the chart.
- Reducto cost equals saved credits multiplied by the fixed 2026-07-28 Standard list rate of `$0.015` per credit.
- Claude cost equals the complete sum of all per-sample `estimated_api_cost_usd` values and is unavailable if any sample cost is missing.
- Bonsai is `$0.00` for the hosted Together endpoint advertised as free, not a local run.
- Highlight all ties at displayed precision using the existing yellow signal palette.
- Keep the default exact-recall ordering and rank numbers, but remove all overall-leader treatments.
- Do not push the branch.

---

### Task 1: Derive full-run costs from saved metadata

**Files:**
- Modify: `benchmarks/tests/test_leaderboard_export.py`
- Modify: `benchmarks/export_leaderboard_space.py`

**Interfaces:**
- Consumes: a `RUNS` entry, its loaded `run_metadata.json`, and the expected document count.
- Produces: `derive_full_run_cost(run: dict, metadata: dict, expected_samples: int) -> dict` with `full_run_cost_usd`, `full_run_cost_source`, and `full_run_cost_explanation`.

- [ ] **Step 1: Write failing cost-derivation tests**

Add tests that assert:

```python
claude = derive_full_run_cost(
    {"cost_source": "claude_api_equivalent"},
    {"samples": {"a": {"estimated_api_cost_usd": 1.25}, "b": {"estimated_api_cost_usd": 2.75}}},
    expected_samples=2,
)
assert claude["full_run_cost_usd"] == 4.0
assert len(claude["full_run_cost_explanation"].split(".")) <= 2
```

Also assert that one missing Claude sample cost yields `None`, Reducto converts
`3108.0628225` credits to `46.6209423375`, Bonsai yields `0.0`, and an
unavailable GPT run yields `None`.

- [ ] **Step 2: Run the focused tests and verify the expected failure**

Run:

```bash
.venv/bin/python -m pytest benchmarks/tests/test_leaderboard_export.py -q
```

Expected: failures because `derive_full_run_cost` and the cost-source
configuration do not exist.

- [ ] **Step 3: Implement minimal metadata-driven cost derivation**

Add constants:

```python
REDUCTO_CREDIT_PRICE_USD = 0.015
PRICING_OBSERVED_DATE = "2026-07-28"
```

Replace per-token pricing configuration with one of:

```python
"cost_source": "claude_api_equivalent"
"cost_source": "reducto_credits"
"cost_source": "hosted_free"
"cost_source": "unavailable"
```

Implement `derive_full_run_cost`, require a complete Claude sample-cost set,
and return one-sentence explanations for all four sources. Call the helper
from `load_runs()` and pass its result into each loaded model.

- [ ] **Step 4: Run focused tests and verify they pass**

Run:

```bash
.venv/bin/python -m pytest benchmarks/tests/test_leaderboard_export.py -q
```

Expected: all cost-derivation tests pass; remaining legacy token-price tests
may still fail until Task 2.

- [ ] **Step 5: Commit the cost data layer**

```bash
git add benchmarks/export_leaderboard_space.py benchmarks/tests/test_leaderboard_export.py
git commit -m "Derive leaderboard full-run costs"
```

---

### Task 2: Render full-run cost and metric-leading cells

**Files:**
- Modify: `benchmarks/tests/test_leaderboard_export.py`
- Modify: `benchmarks/export_leaderboard_space.py`

**Interfaces:**
- Consumes: exported result dictionaries containing the three full-run cost fields and all existing metric values.
- Produces: `format_full_run_cost(value: float | None) -> str` and `metric_leaders(results: list[dict]) -> dict[str, set[int]]`, where sets contain result indexes whose displayed values lead their metric.

- [ ] **Step 1: Replace legacy presentation tests with failing full-run-cost tests**

Assert that:

```python
assert format_full_run_cost(44.86076025) == "$44.86"
assert format_full_run_cost(0.0) == "$0.00"
assert format_full_run_cost(None) == "n/a"
```

Add an HTML fixture with visible ties and assert:

- The `Full-run cost` header and sort key are present.
- Every row has one cost explanation button.
- Unknown values retain `data-sort-missing='true'`.
- All displayed ties have `metric-best`; non-leaders do not.
- `Leader`, `leader-badge`, `winner`, and `point leader` are absent.
- The cost definition and every row explanation contain at most one sentence.

- [ ] **Step 2: Run the focused tests and verify the expected failures**

Run:

```bash
.venv/bin/python -m pytest benchmarks/tests/test_leaderboard_export.py -q
```

Expected: failures on legacy token-price markup, missing cost formatting, and
missing metric-best cells.

- [ ] **Step 3: Implement cost formatting, tie detection, and table markup**

Update `build_data()` to emit the new full-run cost fields and remove
`combined_token_price`. Implement displayed-value keys:

```python
DISPLAYED_METRICS = {
    "full_run_cost_usd": ("min", lambda value: round(value, 2)),
    "exact_record_recall": ("max", lambda value: round(value * 100, 1)),
    "complete_documents": ("max", int),
    "structural_exact_recall": ("max", lambda value: round(value * 100, 1)),
    "scale_control_exact_recall": ("max", lambda value: round(value * 100, 1)),
    "weighted_f1": ("max", lambda value: round(value * 100, 1)),
}
```

Apply `metric-best` only to the matching metric cells. Render each cost as a
value plus an accessible definition button carrying its one-sentence
explanation. Rename the header, sort key, and definition.

- [ ] **Step 4: Replace overall-winner CSS with cell-only signal styling**

Remove winner-row, leader-badge, and chart-leader rules. Add:

```css
td.metric-best {
  background: rgba(255,225,0,.16);
  font-weight: 600;
}
tbody > tr[data-result-row]:hover td.metric-best {
  background: rgba(255,225,0,.24);
}
```

Keep all non-winning cells and rows on the existing palette without new color
tokens.

- [ ] **Step 5: Run focused tests and verify they pass**

Run:

```bash
.venv/bin/python -m pytest benchmarks/tests/test_leaderboard_export.py -q
```

Expected: all table, formatting, sorting, and metric-leader tests pass.

- [ ] **Step 6: Commit the table presentation**

```bash
git add benchmarks/export_leaderboard_space.py benchmarks/tests/test_leaderboard_export.py
git commit -m "Show full-run costs and metric leaders"
```

---

### Task 3: Plot known full-run costs and include Reducto

**Files:**
- Modify: `benchmarks/tests/test_leaderboard_export.py`
- Modify: `benchmarks/export_leaderboard_space.py`

**Interfaces:**
- Consumes: all leaderboard result rows.
- Produces: `build_cost_chart(results: list[dict]) -> str` plotting only rows with numeric `full_run_cost_usd`.

- [ ] **Step 1: Write failing chart tests**

Create a fixture with Bonsai, Opus, Fable, two Reducto rows, and two unknown
GPT rows. Assert:

- Both Reducto model names appear in the SVG.
- Neither GPT model appears in the SVG.
- The axis title is `Full-run cost (USD)`.
- The SVG accessibility text includes cost and explanation.
- No point has a leader class.
- Generated HTML states `5 priced runs shown · 2 runs omitted because cost usage is unavailable`.

- [ ] **Step 2: Run focused tests and verify the expected failures**

Run:

```bash
.venv/bin/python -m pytest benchmarks/tests/test_leaderboard_export.py -q
```

Expected: failures because the chart still consumes `combined_token_price` and
omits Reducto.

- [ ] **Step 3: Implement the full-run-cost chart**

Filter on `full_run_cost_usd is not None`, derive the x-axis maximum by rounding
the largest cost up to the next `$25`, render six evenly spaced ticks, and use
the new axis and ARIA copy. Add fixed label offsets for Opus and both Reducto
points, plus a `<title>` element on every point containing its short
cost explanation. Generate the shown/omitted count from the input rows.

- [ ] **Step 4: Run focused tests and verify they pass**

Run:

```bash
.venv/bin/python -m pytest benchmarks/tests/test_leaderboard_export.py -q
```

Expected: all exporter tests pass.

- [ ] **Step 5: Commit the chart**

```bash
git add benchmarks/export_leaderboard_space.py benchmarks/tests/test_leaderboard_export.py
git commit -m "Plot accuracy against full-run cost"
```

---

### Task 4: Regenerate and verify the complete leaderboard

**Files:**
- Generated and ignored: `dist/huggingface/leaderboard_space/index.html`
- Generated and ignored: `dist/huggingface/leaderboard_space/leaderboard_data.json`

**Interfaces:**
- Consumes: committed exporter code and all released result bundles.
- Produces: a validated local static leaderboard.

- [ ] **Step 1: Run the complete test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass, with only previously known third-party warnings.

- [ ] **Step 2: Regenerate the static leaderboard**

Run:

```bash
make hf-leaderboard
```

Expected: `README.md`, `index.html`, and `leaderboard_data.json` are written.

- [ ] **Step 3: Validate generated data**

Confirm the JSON has seven rows, five numeric full-run costs, two `null` costs,
both Reducto costs, and one-sentence explanations for all seven rows.

- [ ] **Step 4: Verify in the in-app browser**

Reload `http://127.0.0.1:8765/` and confirm all requirements from the design:
five readable chart points, both Reducto points, GPT `n/a` hints, no overall
leader, correct highlighted cells and displayed ties, missing-last cost
sorting in both directions, and no console errors.

- [ ] **Step 5: Run final repository checks**

Run:

```bash
git diff --check
git status --short --branch
git log -5 --oneline --decorate
```

Expected: no whitespace errors, only the user's unrelated untracked paths
remain, and the implementation commits are local on
`codex/add-reducto-results`.
