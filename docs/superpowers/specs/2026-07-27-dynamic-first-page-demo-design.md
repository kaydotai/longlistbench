# Dynamic First-Page Bonsai Demo

## Goal

Make the demo preview, extraction input, and field highlights come from the
exact PDF uploaded by the user. Process only the uploaded PDF's first page.
Remove the committed preview PNG and all fixed rectangle coordinates.

## Demo document

Add a one-page demo PDF containing the first certified driving record currently
found on page 10 of `data/pdfs/driver_mvr_packet_001.pdf`. Store it with the
demo and document its path in the README. The runtime will not special-case its
filename or checksum; it is simply the recommended document for recording the
demo.

## Runtime data flow

1. The browser uploads one PDF to `POST /api/extract`.
2. The server validates the request size, PDF media type, and PDF structure.
3. Poppler processes page 1 only:
   - `pdftotext -raw` supplies the text sent to Bonsai.
   - `pdftotext -bbox-layout` supplies page dimensions and word rectangles.
   - `pdftocairo` renders page 1 to a 150-DPI PNG.
4. The server clears llama.cpp slot 0 to preserve a cold-prefill measurement.
5. The NDJSON stream begins with a `started` event containing the rendered PNG
   as a data URL and the page number.
6. Bonsai streams strict-schema field values.
7. Each non-null value is matched to word rectangles from the uploaded page.
   Matching uses normalized word sequences plus semantic field-label anchors,
   never fixed pixel or percentage coordinates. Repeated values select the
   occurrence nearest their field label.
8. Field events include an optional normalized rectangle. The browser creates
   and positions highlight elements from those rectangles.
9. Missing or unmatched values remain visible in the JSON output without a
   highlight.

The upload exists only in request memory and a temporary processing directory.
No uploaded PDF or rendered preview is persisted.

## UI behavior

The initial workspace contains an empty image element and no highlight
rectangles. After upload, the first streamed event installs the generated page
preview. Subsequent field events animate values and their matching rectangles.
The status copy says "Page 1" and the extraction request has no page query
parameter.

The existing compact horizontal layout, field streaming animation, reset
behavior, model metrics, and local-inference presentation remain unchanged.

## Error handling

- Reject oversized bodies, non-PDF media types, cross-origin requests, invalid
  PDFs, and PDFs without embedded first-page text.
- Report Poppler rendering or layout-extraction failures before model
  inference.
- If a value cannot be located visually, stream the value without a rectangle.
- Scanned PDFs remain out of scope because this demo uses embedded PDF text.

## Tests

- A PDF ingestion test proves that page 1 text, layout words, dimensions, and a
  real PNG preview come from uploaded bytes.
- A one-page sample test verifies the committed demo PDF has exactly one page.
- Service tests use arbitrary valid PDF bytes rather than a checksum allowlist.
- Streaming tests verify the `started` event carries the dynamic preview and
  that field events carry normalized rectangles when matched.
- Matching tests cover repeated values, missing values, and semantic label
  anchors.
- UI tests reject static `/page-10.png`, fixed highlight classes, and fixed
  percentage coordinates.
- Runtime tests require both `pdftotext` and `pdftocairo`.
- The full repository test suite, a no-Poppler CI simulation, a real Bonsai
  extraction, and a rendered visual inspection of the one-page PDF must pass.
