# LongListBench

[![DOI](https://img.shields.io/badge/DOI-10.57967%2Fhf%2F9768-blue)](https://doi.org/10.57967/hf/9768)

[Paper](https://huggingface.co/datasets/kaydotai/LongListBench/blob/main/longlistbench.pdf) | [Hugging Face dataset](https://huggingface.co/datasets/kaydotai/LongListBench) | [Leaderboard](https://huggingface.co/spaces/kaydotai/LongListBench-Leaderboard) | [Release v2.2.1](https://github.com/kaydotai/longlistbench/releases/tag/v2.2.1)

Benchmark for long-list entity extraction from complex semi-structured business PDFs, including dense layouts, OCR transcripts, and long-range cross-page evidence.

This benchmark was developed at [Kay.ai](https://kay.ai).

LongListBench evaluates complete per-document extraction: give a system one PDF or OCR transcript plus the target output contract, then measure exact records and fully complete documents. Structured operations families are scale and completeness controls; claim and policy packets add distant evidence, inherited context, and heterogeneous schemas.

## Quick Start

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
python -m pip install -r benchmarks/requirements.txt
python -m playwright install chromium

# Set API keys (only needed for OCR/evaluation runs)
cp .env.example .env

# Inspect the released dataset artifacts
open data/index.html

# Run OCR/evaluation only when regenerating transcripts or baselines
python benchmarks/ocr_claims_pdfs.py \
  --ocr-engine gemini \
  --model gemini-3.5-flash
```

## Reproducibility

Convenience targets are provided via the repository root `Makefile`:

```bash
make help

# Create venv + install deps + install Playwright Chromium
make setup

# Regenerate all 26 synthetic core-operation documents under tmp/
make generate-core-operations

# Build dataset indexes from the current data/ directory
python benchmarks/build_instance_index.py --input data

# Build the paper
make paper
```

See [`benchmarks/README.md`](benchmarks/README.md) for benchmark documentation and
[`benchmarks/core_operations/README.md`](benchmarks/core_operations/README.md) for
the public synthetic generators and templates.

## Hugging Face Dataset Package

The repository can export a LongArray-style Hugging Face dataset package with one row per PDF, embedded PDF bytes, JSON ground truth, metadata, and available transcripts:

```bash
source .venv/bin/activate
python -m pip install -r benchmarks/requirements-hf.txt

make hf-export
```

By default this writes an ignored local package to `dist/huggingface/longlistbench/` for `kaydotai/LongListBench`. Override the target repo ID with:

```bash
HF_REPO_ID=your-org/your-dataset make hf-export
```

Publishing to `kaydotai/LongListBench` is automated: the `Dataset Publish` workflow rebuilds the
package whenever `data/`, `benchmarks/results/`, the export script, or `VERSION` changes, and
uploads it on `main`. Pull requests build the package and attach the generated card as an artifact
without uploading. Use the workflow's manual trigger to republish without a source change. Local
`make hf-export` remains available for inspecting the package before it ships.

The exported Hugging Face configs are:

| Config | Contents |
|--------|----------|
| `core_operations` | 26 production-like commercial insurance and trucking-operation PDFs with dense repeated operations, IFTA, and loss-run records |
| `claim_multihop` | 3 claim PDFs requiring long-range cross-page joins |
| `policy_packets` | 3 long BOP, WC, and CGL policy packets requiring cross-page extraction |

Upload only after inspecting the generated package:

```bash
python benchmarks/export_hf_dataset.py \
  --input data \
  --output dist/huggingface/longlistbench \
  --repo-id kaydotai/LongListBench \
  --overwrite \
  --upload
```

## Leaderboard Space

The [leaderboard](https://huggingface.co/spaces/kaydotai/LongListBench-Leaderboard) is a static
Hugging Face Space generated from the saved evaluation reports in `benchmarks/results/`:

```bash
make hf-leaderboard
```

This writes an ignored local package to `dist/huggingface/leaderboard_space/`. Upload only after
inspecting the generated files:

```bash
python benchmarks/export_leaderboard_space.py --overwrite --upload
```

To add a result, verify that the submitted scores reproduce from the saved predictions, add the run
directory to `RUNS` in `benchmarks/export_leaderboard_space.py`, then rebuild and upload.

## Versioning and Citation

- **Version**: see `VERSION`.
- **Citation metadata**: see `CITATION.cff`.
- **DOI**: [10.57967/hf/9768](https://doi.org/10.57967/hf/9768) (Hugging Face dataset release, includes the paper PDF).

## Benchmark Overview

- **32 benchmark instances** across 13 production-like document families
- **29,599 target records** across commercial operations, claim, and policy extraction tasks
- **26 core operations PDFs** covering IFTA, driver/MVR, vehicle schedule, and loss-run layouts
- **3 policy PDFs** covering long BOP, WC, and CGL policy packets
- **3 claim cross-page PDFs** requiring long-range joins within a single document
- **Ground truth annotations** in JSON format
- **OCR transcripts** generated from rendered PDF page images
- **OCR support validation**: 100.0% average identifier coverage, 100.0% tracked identifier-field support, no records with a missing tracked identifier, and an audited 56/76,968 numeric-field OCR miss set
- **Synthetic visible values only**; private production documents were used only as visual layout references

## Dataset Layout

Released artifacts are organized by modality under `data/`:

```text
data/
  manifest.json
  pdfs/{sample_id}.pdf
  html/{sample_id}.html
  ground_truth/{sample_id}.json
  transcripts/ocr_gemini/{sample_id}.md
  metadata/{sample_id}.json
  schemas/*.schema.json
```

`data/manifest.json` is the source of truth for sample IDs, document families, artifact paths, transcript availability, and per-sample metadata.

### Document Families

| Family | PDFs | Target records |
|--------|-----:|---------------:|
| `ifta_mileage_by_vehicle` | 8 | 17,565 |
| `ifta_multisection_return_packet` | 2 | 796 |
| `ifta_return_schedule_details` | 3 | 2,737 |
| `ifta_tax_return_summary` | 2 | 1,520 |
| `driver_mvr_request_and_roster` | 3 | 1,260 |
| `loss_run_external` | 3 | 900 |
| `vehicle_schedule_spreadsheet_export` | 2 | 1,600 |
| `ifta_tax_return_inquiry_detail` | 2 | 1,300 |
| `driver_schedule_spreadsheet_export` | 1 | 500 |
| `claim_crosspage_multihop` | 3 | 77 |
| `policy_multihop_bop` | 1 | 344 |
| `policy_multihop_wc` | 1 | 438 |
| `policy_multihop_cgl` | 1 | 562 |

### Complexity Stressors

LongListBench defines 14 canonical cross-cutting stressors, stored as applicable subsets in each instance's `problems` metadata. The manifest contains 45 distinct problem tokens because it also retains finer domain and implementation tags for audit slices.

| Tag | Meaning |
|-----|---------|
| `page_breaks` | Target lists or supporting sections span page boundaries with repeated headers or inherited context. |
| `split_records` | One target record has fields in separate visual blocks, sections, or pages and must be assembled. |
| `multi_row` | One logical record contains wrapped notes, long descriptions, clause prose, or continuation rows. |
| `duplicates` | Duplicate or near-duplicate distractor material appears, usually as prior-term/archive sections rather than exact duplicate target rows. |
| `large_doc` | Documents contain hundreds to thousands of targets or enough pages to expose truncation/list-completeness failures. |
| `multiple_tables` | Target records are mixed with summaries, ledgers, support tables, schedules, or empty/no-claims tables. |
| `multi_column` | Two-column or form-like layouts stress reading order. |
| `merged_cells` | Tables use merged cells, section-spanning rows, or `colspan`/`rowspan` structure. |
| `ocr_condition` | Released transcripts are OCR output from rendered PDF page images. |
| `ocr_layout_condition` | OCR preserves visual spacing and reading order instead of converting tables into clean CSV-style rows. |
| `long_range_evidence` | Required fields must be joined from distant sections of the same PDF. |
| `cross_section_join` | A target record must be assembled from separately labeled sections, such as return summary, distance/gallon schedules, and liability schedules. |
| `repeated_keys` | Common keys such as states or jurisdictions repeat across sections or returns, so the key alone is insufficient for matching. |
| `heterogeneous_record_list` | One output list contains multiple schema families, especially in policy packets. |

These tags are present in `data/manifest.json`, `data/metadata/{sample_id}.json`, the browsable `data/index.html`, and the Hugging Face export.

The PDFs do not print these labels, but the stressors are visible in the document structure. This map gives representative pages to inspect; the full per-instance mapping is in the metadata.

| Stressor | Representative PDF/pages | What to check |
|----------|--------------------------|---------------|
| `page_breaks` | `ifta_mileage_by_vehicle_001`, pages 2-3 | Unit 9215 continues onto the next page under repeated report context. |
| `split_records` | `ifta_multisection_return_001`, pages 1, 2, and 4 | One jurisdiction record combines return-header context, Schedule A mileage/gallons, and later tax-detail fields. |
| `multi_row` | `loss_run_external_001`, pages 1-2; `driver_mvr_packet_001`, page 10 | Claim rows include description/detail rows; driver records include roster/MVR detail blocks. |
| `duplicates` | `loss_run_external_001`, pages 1-2; `multihop_bop_012_001`, pages 45-68 | Summary/no-claim rows and archived forms create near-duplicate distractors. |
| `large_doc` | `ifta_mileage_by_vehicle_008`, whole PDF; `mixed_cgl_040_001`, whole PDF | Long files with 76 and 133 pages respectively, including thousands of operation rows or many policy records. |
| `multiple_tables` | `ifta_tax_inquiry_001`, page 1; `loss_run_external_001`, pages 1-2 | Target tables appear alongside support tables, empty tables, summaries, and section totals. |
| `multi_column` | `mixed_cgl_040_001`, pages 67-86; `multihop_wc_025_001`, pages 54-73 | Material policy provisions are laid out in two-column policy-form pages. |
| `merged_cells` | `loss_run_external_001`, page 1; `ifta_mileage_by_vehicle_002`, page 2 | Section-spanning detail rows and inherited unit bands interrupt regular row structure. |
| `ocr_condition` | Any PDF with `data/transcripts/ocr_gemini/{sample_id}.md`, for example `loss_run_external_001`, page 1 | The released text input is OCR output from rendered page images, not the HTML text layer. |
| `ocr_layout_condition` | `ifta_multisection_return_001`, pages 2 and 4 | OCR preserves the visual Schedule A table and dense Jurisdictions tax-detail table instead of a clean row table. |
| `long_range_evidence` | `multihop_012_001_crosspage`, pages 3, 26, 28, 46, 47, 60; `mixed_040_001_crosspage`, pages 3, 50, 54, 96, 97, 137 | A front claim row must be joined to driver, policy, cause-code, claimant, and ledger sections far apart in one PDF. |
| `cross_section_join` | `ifta_multisection_return_001`, pages 1, 2, 4 | Each jurisdiction row combines return header context, Schedule A mileage/gallon values, and Jurisdictions tax-detail values while ignoring adjustment/support rows. |
| `repeated_keys` | `ifta_multisection_return_001`, pages 2, 4, 8, 10 | The same jurisdiction codes recur across returns and sections, so state code alone is not a unique row key. |
| `heterogeneous_record_list` | `multihop_bop_012_001`, pages 2-17 and 39-90; `mixed_cgl_040_001`, pages 2-25 and 54-133 | One output list mixes locations/classifications, coverage items, forms, endorsements, premiums, and clause records. |

### Multi-Hop Extensions

The repository includes two single-document cross-page multi-hop suites in the same `data/` layout.

The claim multi-hop suite has 3 PDFs and 77 target incidents. These cases keep the same incident schema, but required fields are spread across distant sections of one long PDF. The primary claim schedule appears near the front; supporting rosters, policy registers, cause-code appendices, claimant indexes, and financial ledgers appear dozens to hundreds of pages later with dense distractor pages in between.

| Join key | Distant section |
|----------|-----------------|
| `policy_number` | Policy register |
| `unit_number` | Driver roster |
| `cause_code` | Cause classification appendix |
| `incident_number` | Claimant index and financial ledger |

The cross-page PDFs are:

| Sample | Pages | Target incidents |
|--------|-------|------------------|
| `multihop_012_001_crosspage` | 61 | 12 |
| `multihop_025_001_crosspage` | 99 | 25 |
| `mixed_040_001_crosspage` | 148 | 40 |

Join/evidence metadata is recorded in `data/metadata/{sample_id}.json`; the rendered documents do not expose benchmark instructions such as "join on" labels.

The policy suite has 3 commercial insurance policy PDFs and 1,344 target policy records. A policy packet is the contract document issued by an insurer; it combines declarations, covered locations or classifications, coverage limits and deductibles, rating or premium schedules, required forms, material policy clauses, and endorsements that modify the base policy. The samples cover Businessowners Policy (BOP), Workers Compensation (WC), and Commercial General Liability (CGL) schemas inspired by real policy-review workflows. The visible document content is synthetic, but the packet structure mirrors observed commercial policy packets.

Interpret the configs separately. `core_operations` contains high-density structured reports where deterministic row parsers or document-specific agent code can perform well; those files measure scale, OCR preservation, and output completeness. The multisection IFTA files within `core_operations` add OCR-layout preservation and cross-section joins. The claim and policy packet configs are the stronger complex packet cases, with inherited context, heterogeneous record types, distant supporting sections, and distractor material.

OCR support should be interpreted at the affected-record and field level, not only by unique identifier coverage. The identifier validation finds every tracked identifier across all 29,599 targets. The numeric audit checks every ground-truth value with absolute value at least 10 and records 56 genuine OCR misses among 76,968 checked numeric fields (0.073%). The released transcript is not hand-corrected; `data/ocr_numeric_fidelity_baseline.json` makes the exact miss set reproducible. These checks do not score extraction quality by themselves. The evaluator compares complete normalized records first and reports flattened field-value overlap as secondary partial credit.

| Sample | Pages | Target policy records |
|--------|-------|-----------------------|
| `multihop_bop_012_001` | 99 | 344 |
| `multihop_wc_025_001` | 108 | 438 |
| `mixed_cgl_040_001` | 133 | 562 |

## Saved Evaluation Artifacts

Saved reports under `benchmarks/results/` should be treated as local run artifacts unless their manifest hash matches the current `data/manifest.json`. After replacing layouts, rerun OCR and evaluation before citing current-layout or current-model baselines. The current released dataset includes OCR transcripts for every PDF.

The repository includes six full-corpus repository-denied coding-agent runs under the same OCR input and field-contract protocol. Each result directory includes all 32 predictions, input and prediction fingerprints, and a report that can be checked offline. The paper compares GPT-5.6-Sol, Fable 5, GPT-5.5, and Opus 4.8; GPT-5.6-Terra and GPT-5.6-Luna are additional leaderboard results.

| Agent | Documents | Target records | Errors | Exact-record recall | Complete documents | Field micro-F1 | Field macro-F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Codex CLI `gpt-5.6-sol`, xhigh | 32 | 29,599 | 0 | 97.9% | 8/32 (25.0%) | 99.4% | 99.4% |
| Codex CLI `gpt-5.6-luna`, xhigh | 32 | 29,599 | 0 | 98.1% | 5/32 (15.6%) | 99.5% | 98.8% |
| Codex CLI `gpt-5.6-terra`, xhigh | 32 | 29,599 | 0 | 94.5% | 5/32 (15.6%) | 99.0% | 98.4% |
| Claude Code `claude-fable-5`, xhigh | 32 | 29,599 | 0 | 95.1% | 9/32 (28.1%) | 96.8% | 93.6% |
| Codex CLI `gpt-5.5`, xhigh | 32 | 29,599 | 0 | 94.5% | 4/32 (12.5%) | 98.8% | 98.6% |
| Claude Code `claude-opus-4-8`, xhigh | 32 | 29,599 | 0 | 97.7% | 7/32 (21.9%) | 99.4% | 99.3% |

The latest saved results are under `benchmarks/results/codex_gpt56_sol_full_current_ocr_v2/`, `benchmarks/results/codex_gpt56_luna_full_current_ocr_v2/`, `benchmarks/results/codex_gpt56_terra_full_current_ocr_v2/`, and `benchmarks/results/claude_fable5_full_current_ocr_v2/`; the GPT-5.5 and Opus 4.8 comparison runs remain available beside them. Luna's preselected leaderboard run reached 98.1% exact recall and 5/32 complete documents. Across three matched Luna runs, exact recall ranged from 91.4% to 98.1% and complete-document success from 4/32 to 6/32. Terra's corresponding ranges were 94.5% to 98.1% and 5/32 to 7/32. Neither leaderboard result selects the best repeat.

An exact record must match every normalized target field. Complete-document success requires the predicted and ground-truth record multisets to be identical, including duplicates and with no extra records. Record order is not scored. Field-pair F1 remains a secondary partial-credit diagnostic.

The evaluator uses a fixed document-family mapping for scale-control and structural-challenge roles:

| Evaluation role | Documents | Target records | GPT-5.6-Sol exact | Fable 5 exact | GPT-5.6-Sol complete | Fable 5 complete |
|---|---:|---:|---:|---:|---:|---:|
| Structural challenges | 19 | 8,414 | 93.8% | 84.0% | 4/19 (21.1%) | 5/19 (26.3%) |
| Scale controls | 13 | 21,185 | 99.5% | 99.5% | 4/13 (30.8%) | 4/13 (30.8%) |

Strict exact-record recall for the latest models, labeled by the extraction problem each family emphasizes:

| Extraction problem | Documents | Target records | GPT-5.6-Sol | Fable 5 |
|---|---:|---:|---:|---:|
| Sparse record enrichment (driver/MVR) | 3 | 1,260 | 99.4% | 100.0% |
| Long-range claim joins | 3 | 77 | 98.7% | 98.7% |
| Split return schedules | 3 | 2,737 | 95.5% | 95.5% |
| Mixed row/detail loss runs | 3 | 900 | 97.3% | 92.2% |
| Tax inquiry detail tables | 2 | 1,300 | 99.9% | 99.8% |
| Heterogeneous policy records | 3 | 1,344 | 73.3% | 14.6% |
| Cross-section return joins | 2 | 796 | 99.6% | 99.6% |
| Tax-summary scale controls | 2 | 1,520 | 99.5% | 99.5% |
| Driver-schedule scale control | 1 | 500 | 99.8% | 99.8% |
| Mileage-by-vehicle scale controls | 8 | 17,565 | 99.4% | 99.4% |
| Vehicle-schedule scale controls | 2 | 1,600 | 100.0% | 100.0% |

Full-context one-shot prompting is not treated as a full-corpus protocol for this release. It is useful as a lower-bound stress test, but the largest documents can hit model output limits or latency timeouts before returning a scoreable complete list.

For all released runs, claim tasks received the published JSON Schema. Generic tasks received sample-specific field names and record groups derived from ground-truth object structure. This disclosed the output schema but not target values or counts. Each temporary workspace contained only the OCR transcript, field contract, prompt, and output directory; the macOS sandbox denied the benchmark repository, and the prompt prohibited other host files. This was repository isolation rather than a host-wide filesystem allowlist. Scoring normalizes whitespace, dates, decimals, accounting negatives, string case, documented region/fuel/line-of-business/clause-scope representations, visible `Unit` prefixes in vehicle identifiers, and `Quarter Return`/`Quarterly Return` heading aliases before comparing complete records and secondary field-value pairs. Extra heading context is not discarded.

The corrected driver/MVR family was rerun on July 21, 2026 under the same model and isolation settings; predictions for the 29 unchanged document inputs were replayed from the July 14 runs. Per-sample fingerprints and prediction hashes in each result directory identify which inputs were rerun.

## Development Setup

### Installing the Pre-Commit Hook

Optional: install a pre-commit hook to quickly sanity-check that the paper compiles:

```bash
# From the repository root
cp pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

The hook runs a fast LaTeX compile (`make quick`) in the `paper` directory; in strict mode it can prevent the commit if compilation fails.

By default, the hook is best-effort and will skip (or warn) when dependencies are missing. To make paper compilation failures block commits, set:

```bash
export STRICT_PAPER_COMPILE=1
```

**Manually invoking the hook:**
```bash
# Test the hook without committing
.git/hooks/pre-commit
```

Alternatively, run the same check from your virtualenv:
```bash
source .venv/bin/activate
make -C paper quick
```

**Note:** You can skip the hook for a specific commit using:
```bash
git commit --no-verify
```

### Paper Build Only

LaTeX is only needed if you want to compile the paper locally.

- LaTeX distribution (TeX Live, MacTeX, or similar)
- `pdflatex` and `biber` available in your `PATH`
- See [paper/README.md](paper/README.md) for paper-specific build instructions
