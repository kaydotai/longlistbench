# Dynamic First-Page Bonsai Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the uploaded PDF's first page the sole source of the preview, Bonsai input, and field highlight rectangles.

**Architecture:** A focused `pdf_page.py` module uses Poppler to extract first-page text and word geometry and render a PNG in a temporary directory. The existing server streams that generated preview, then attaches dynamically matched normalized rectangles to Bonsai field events; the browser creates overlays from those rectangles.

**Tech Stack:** Python 3.10+, Poppler (`pdftotext`, `pdftocairo`, `pdfinfo`, `pdfseparate`), stdlib HTTP server, OpenAI-compatible streaming, HTML/CSS/JavaScript, pytest.

## Global Constraints

- Process page 1 only.
- Accept uploaded PDFs by content and Poppler validation, not filename or checksum.
- Persist neither uploaded bytes nor generated previews.
- Use normalized word geometry and semantic labels; never fixed pixel or percentage coordinates.
- Missing or unmatched values render without a rectangle.
- Scanned PDFs without embedded first-page text remain unsupported.
- Preserve same-origin and `application/pdf` request checks.
- Preserve cold-prefill slot erasure before every inference.

---

### Task 1: First-page PDF ingestion

**Files:**
- Create: `demo/bonsai_extract/pdf_page.py`
- Modify: `tests/test_bonsai_demo_server.py`

**Interfaces:**
- Produces: `PageWord`, `UploadedPage`, and `ingest_first_pdf_page(pdf_bytes: bytes) -> UploadedPage`.
- `UploadedPage` contains `text: str`, `width: float`, `height: float`, `words: tuple[PageWord, ...]`, and `preview_png: bytes`.

- [ ] **Step 1: Write failing ingestion tests**

Add tests that call `ingest_first_pdf_page` with the existing multi-page packet
and assert that only its first page is returned:

```python
page = ingest_first_pdf_page(SAMPLE_PDF.read_bytes())
assert page.text.startswith("ATTN: SAFETY OPERATIONS")
assert "Report of Services Provided" in page.text
assert "ROSA NGUYEN" not in page.text
assert page.width == pytest.approx(594.96)
assert page.height == pytest.approx(841.92)
assert any(word.text == "ATTN:" for word in page.words)
assert page.preview_png.startswith(b"\x89PNG\r\n\x1a\n")
```

The absence of `ROSA NGUYEN`, which appears on page 10, proves that ingestion
does not leak text from later pages. Task 5 creates and verifies the one-page
Rosa demo PDF.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_bonsai_demo_server.py::test_uploaded_pdf_ingestion_returns_first_page_text_layout_and_preview
```

Expected: collection fails because `pdf_page` does not exist.

- [ ] **Step 3: Implement the ingestion module**

Define:

```python
@dataclass(frozen=True)
class PageWord:
    text: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float

@dataclass(frozen=True)
class UploadedPage:
    text: str
    width: float
    height: float
    words: tuple[PageWord, ...]
    preview_png: bytes

def ingest_first_pdf_page(pdf_bytes: bytes) -> UploadedPage:
    ...
```

Use one `TemporaryDirectory`. Write the request body to `upload.pdf`, run
`pdftotext -f 1 -l 1 -raw`, run `pdftotext -f 1 -l 1 -bbox-layout`, parse the
XHTML page and word nodes with `xml.etree.ElementTree`, and run
`pdftocairo -f 1 -l 1 -png -singlefile -r 150`. Raise `ValueError` with a
short user-facing message for invalid PDFs, missing first-page text, missing
geometry, or rendering failure.

- [ ] **Step 4: Run ingestion tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_bonsai_demo_server.py -k ingestion
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add demo/bonsai_extract/pdf_page.py tests/test_bonsai_demo_server.py
git commit -m "Add dynamic first-page PDF ingestion"
```

### Task 2: Dynamic semantic rectangle matching

**Files:**
- Modify: `demo/bonsai_extract/pdf_page.py`
- Modify: `tests/test_bonsai_demo_server.py`

**Interfaces:**
- Consumes: `PageWord`, page width, and page height from Task 1.
- Produces: `locate_field_value(page: UploadedPage, field: str, value: object) -> dict[str, float] | None`.
- Rectangle keys are `left`, `top`, `width`, and `height`, each normalized to the inclusive range `0.0..1.0`.

- [ ] **Step 1: Write failing matcher tests**

Create synthetic words with two occurrences of `LA J100 200 300`: one in the
record heading and one beside the `LICENSE NUMBER` label. Assert that:

```python
rect = locate_field_value(page, "license_number", "LA J100 200 300")
assert rect == {
    "left": pytest.approx(0.31),
    "top": pytest.approx(0.40),
    "width": pytest.approx(0.19),
    "height": pytest.approx(0.02),
}
assert locate_field_value(page, "date_hired", None) is None
assert locate_field_value(page, "name", "NOT PRESENT") is None
```

Add anchor cases for `FULL NAME`, `DATE OF BIRTH`, `LICENSE CLASS`,
`JURISDICTION`, `Accidents`, `Moving violations`, and `Run`.

- [ ] **Step 2: Run matcher tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_bonsai_demo_server.py -k rectangle
```

Expected: import or attribute failure for `locate_field_value`.

- [ ] **Step 3: Implement the matcher**

Add exact semantic label aliases:

```python
FIELD_LABELS = {
    "name": ("FULL NAME",),
    "date_of_birth": ("DATE OF BIRTH",),
    "license_class": ("LICENSE CLASS",),
    "license_number": ("LICENSE NUMBER",),
    "state_licensed": ("JURISDICTION",),
    "accidents_last_5_years": ("Accidents",),
    "mvr_violations": ("Moving violations",),
    "mvr_run_date": ("Run",),
}
```

Normalize whitespace and case only. Find contiguous word sequences matching the
field value. For fields with labels, find matching label sequences and choose
the value occurrence with the smallest Euclidean distance from a label center,
preferring values below or to the right of the label. Union the chosen value
word boxes and normalize by the Poppler page dimensions.

- [ ] **Step 4: Run matcher and ingestion tests**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_bonsai_demo_server.py -k "rectangle or ingestion"
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add demo/bonsai_extract/pdf_page.py tests/test_bonsai_demo_server.py
git commit -m "Match extracted values to uploaded PDF geometry"
```

### Task 3: Stream the uploaded preview and rectangles

**Files:**
- Modify: `demo/bonsai_extract/app.py`
- Modify: `tests/test_bonsai_demo_server.py`

**Interfaces:**
- Consumes: `ingest_first_pdf_page` and `locate_field_value`.
- `DemoExtractionService.stream_pdf(pdf_bytes: bytes)` returns NDJSON events.
- `started` includes `page_number: 1` and `preview_data_url`.
- Each `field` may include `rectangle`.

- [ ] **Step 1: Rewrite service tests for first-page behavior**

Replace checksum and page-10 expectations with an injected
`page_ingestor: Callable[[bytes], UploadedPage]`. Assert:

```python
started = next(events)
assert started["page_number"] == 1
assert started["preview_data_url"].startswith("data:image/png;base64,")
assert next(field for field in events if field["field"] == "name")["rectangle"]
```

Add a test proving arbitrary PDF bytes reach the ingestor and remove tests that
expect an exact bundled SHA-256.

- [ ] **Step 2: Run service tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_bonsai_demo_server.py -k "streaming or arbitrary"
```

Expected: failures because the service still accepts `page_number=10`, checks
the bundled hash, and does not stream a preview or rectangles.

- [ ] **Step 3: Implement first-page streaming**

Remove `SAMPLE_METADATA`, `expected_pdf_sha256`, `UnsupportedDocumentError`,
`PAGE_IMAGE`, and every page-number argument. Add `page_ingestor` injection.
Build `runner.Page(number=1, text=...)` from `UploadedPage.text`. Base64-encode
`preview_png` into the `started` event. Attach
`locate_field_value(uploaded_page, field, value)` to each non-null field event.
Keep cache erasure after successful ingestion and before model inference.

Simplify `DemoRequestHandler` so `POST /api/extract` has no page query parsing.
Remove `/page-10.png` and `/sample.pdf`.

- [ ] **Step 4: Run service tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_bonsai_demo_server.py
```

Expected: all demo server tests pass.

- [ ] **Step 5: Commit**

```bash
git add demo/bonsai_extract/app.py tests/test_bonsai_demo_server.py
git commit -m "Stream dynamic first-page previews and rectangles"
```

### Task 4: Dynamic browser rendering

**Files:**
- Modify: `demo/bonsai_extract/index.html`
- Modify: `tests/test_bonsai_demo_server.py`

**Interfaces:**
- Consumes: `preview_data_url` from `started` and optional normalized
  `rectangle` from `field`.
- Produces: a preview image and runtime-created `.highlight` elements.

- [ ] **Step 1: Write failing UI source tests**

Assert:

```python
assert 'id="page-image"' in html
assert 'id="highlight-layer"' in html
assert 'src="/page-10.png"' not in html
assert ".h-name" not in html
assert "fieldHighlights" not in html
assert 'fetch("/api/extract",' in html
assert "preview_data_url" in html
assert "event.rectangle" in html
```

- [ ] **Step 2: Run UI test and verify RED**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_bonsai_demo_server.py::test_demo_ui_uses_uploaded_first_page_and_dynamic_rectangles
```

Expected: failure on static image and coordinate classes.

- [ ] **Step 3: Implement dynamic preview and overlay**

Use:

```html
<img id="page-image" alt="Uploaded PDF first page">
<div id="highlight-layer"></div>
```

On `started`, assign `pageImage.src = event.preview_data_url`, set status to
`Page 1`, and reveal the page after the image loads. On a field event with a
rectangle, create one `.highlight`, set its `left`, `top`, `width`, and
`height` from normalized values multiplied by 100, and append it to the
highlight layer. Reset removes every generated highlight and clears the image
source. Remove all fixed highlight classes and the `fieldHighlights` map.

- [ ] **Step 4: Run UI and service tests**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_bonsai_demo_server.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add demo/bonsai_extract/index.html tests/test_bonsai_demo_server.py
git commit -m "Render uploaded PDF preview and highlights dynamically"
```

### Task 5: One-page demo PDF and single-script setup

**Files:**
- Create: `demo/bonsai_extract/assets/driver_mvr_record_001.pdf`
- Delete: `demo/bonsai_extract/assets/driver_mvr_packet_001_page_10.png`
- Modify: `scripts/run_bonsai_demo.sh`
- Modify: `README.md`
- Modify: `tests/test_bonsai_runtime_scripts.py`
- Modify: `tests/test_bonsai_demo_server.py`

**Interfaces:**
- The recommended upload is
  `demo/bonsai_extract/assets/driver_mvr_record_001.pdf`.
- The launcher requires `pdftotext` and `pdftocairo`.

- [ ] **Step 1: Write failing asset and setup tests**

Assert the sample exists, begins with `%PDF`, has one page according to
`pdfinfo`, the old PNG is absent, the launcher checks `pdftocairo`, and README
points to the new sample.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_bonsai_runtime_scripts.py \
  tests/test_bonsai_demo_server.py -k "sample or runtime"
```

Expected: failures for the missing PDF, old PNG, launcher check, and README.

- [ ] **Step 3: Generate the one-page PDF**

Run:

```bash
mkdir -p tmp/pdfs
pdfseparate -f 10 -l 10 \
  data/pdfs/driver_mvr_packet_001.pdf \
  tmp/pdfs/driver_mvr_record_001-%d.pdf
mv tmp/pdfs/driver_mvr_record_001-10.pdf \
  demo/bonsai_extract/assets/driver_mvr_record_001.pdf
```

Delete the old PNG. Add `pdftocairo` to the launcher's command checks. Update
README setup and upload instructions to the new PDF.

- [ ] **Step 4: Render and visually inspect the sample**

Run:

```bash
mkdir -p tmp/pdfs/rendered
pdftoppm -f 1 -l 1 -png -r 150 \
  demo/bonsai_extract/assets/driver_mvr_record_001.pdf \
  tmp/pdfs/rendered/driver_mvr_record
pdfinfo demo/bonsai_extract/assets/driver_mvr_record_001.pdf
```

Inspect `tmp/pdfs/rendered/driver_mvr_record-1.png`. Require one page, intact
text, no clipping, and the complete activity table.

- [ ] **Step 5: Run asset and runtime tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_bonsai_runtime_scripts.py \
  tests/test_bonsai_demo_server.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add README.md scripts/run_bonsai_demo.sh \
  demo/bonsai_extract/assets tests/test_bonsai_runtime_scripts.py \
  tests/test_bonsai_demo_server.py
git commit -m "Add one-page upload-driven Bonsai demo"
```

### Task 6: Full verification and PR update

**Files:**
- Verify all files changed in Tasks 1-5.

**Interfaces:**
- Produces a green update to PR #19.

- [ ] **Step 1: Run static and full test verification**

```bash
sh -n scripts/run_bonsai_demo.sh
git diff --check origin/main...HEAD
.venv/bin/python -m pytest -q
env PATH=/usr/bin:/bin .venv/bin/python -m pytest -q \
  tests/test_bonsai_demo_server.py
```

Expected: shell syntax passes, no diff errors, full suite passes, and the
no-Poppler run skips only integration tests that require Poppler.

- [ ] **Step 2: Run a real local extraction**

Start the PR app against the local llama.cpp server, upload
`driver_mvr_record_001.pdf`, and assert the final event has:

```python
result["page_number"] == 1
result["prompt_tokens"] > 0
result["prefill_tokens_per_second"] > 1
result["candidates"][0]["name"] == "ROSA NGUYEN"
```

Confirm the `started` event contains a PNG data URL and returned field events
contain normalized rectangles.

- [ ] **Step 3: Review for hardcoding**

```bash
rg -n "page-10|h-name|fieldHighlights|driver_mvr_packet_001_page_10.png" \
  demo tests README.md
```

Expected: no runtime or UI references.

- [ ] **Step 4: Push and wait for CI**

```bash
git push
gh pr checks 19 --watch --interval 5
```

Expected: PR #19 remains mergeable and every required check succeeds.
