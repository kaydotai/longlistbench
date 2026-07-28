from __future__ import annotations

from email.message import Message
from html.parser import HTMLParser
from http import HTTPStatus
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from benchmarks import run_bonsai_page_evaluation as runner
from demo.bonsai_extract.app import (
    CompactRowStreamDecoder,
    DemoExtractionService,
    DemoRequestHandler,
    erase_llama_prompt_cache,
)
from demo.bonsai_extract import pdf_page
from demo.bonsai_extract.pdf_page import (
    PageWord,
    UploadedPage,
    ingest_first_pdf_page,
    locate_field_value,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PDF = ROOT / "data" / "pdfs" / "driver_mvr_packet_001.pdf"
DEMO_HTML = ROOT / "demo" / "bonsai_extract" / "index.html"
SAMPLE_PAGE_TEXT = """Certified Employer Driving Record
Run 01/21/2026
FULL NAME
ROSA NGUYEN
DATE OF BIRTH
05/10/1978
LICENSE CLASS
A
LICENSE NUMBER
LA J100 200 300
JURISDICTION
LA
Accidents 0
Moving violations None
"""

_VALID_BBOX_LAYOUT = """<html><body><doc>
<page width="10" height="20"><word xMin="1" yMin="2" xMax="3" yMax="4">FIRST</word></page>
</doc></body></html>"""


def _matcher_page(words: tuple[PageWord, ...]) -> UploadedPage:
    return UploadedPage(
        text="synthetic page",
        width=1,
        height=1,
        words=words,
        preview_png=b"PNG",
    )


def _uploaded_page() -> UploadedPage:
    """Return a first-page fixture with an anchorable extracted name."""

    return UploadedPage(
        text=SAMPLE_PAGE_TEXT,
        width=612,
        height=792,
        words=(
            PageWord("FULL", 0.10, 0.20, 0.17, 0.22),
            PageWord("NAME", 0.18, 0.20, 0.25, 0.22),
            PageWord("ROSA", 0.31, 0.24, 0.37, 0.26),
            PageWord("NGUYEN", 0.38, 0.24, 0.47, 0.26),
        ),
        preview_png=b"\x89PNG\r\n\x1a\npreview",
    )


def test_rectangle_matcher_prefers_value_nearest_its_semantic_label() -> None:
    page = _matcher_page(
        (
            PageWord("LA", 0.25, 0.10, 0.31, 0.12),
            PageWord("J100", 0.32, 0.10, 0.38, 0.12),
            PageWord("200", 0.39, 0.10, 0.43, 0.12),
            PageWord("300", 0.44, 0.10, 0.48, 0.12),
            PageWord("LICENSE", 0.10, 0.36, 0.20, 0.38),
            PageWord("NUMBER", 0.21, 0.36, 0.30, 0.38),
            PageWord("LA", 0.31, 0.40, 0.36, 0.42),
            PageWord("J100", 0.37, 0.40, 0.42, 0.42),
            PageWord("200", 0.43, 0.40, 0.47, 0.42),
            PageWord("300", 0.48, 0.40, 0.50, 0.42),
        )
    )

    rect = locate_field_value(page, "license_number", "LA J100 200 300")

    assert rect == {
        "left": pytest.approx(0.31),
        "top": pytest.approx(0.40),
        "width": pytest.approx(0.19),
        "height": pytest.approx(0.02),
    }
    assert locate_field_value(page, "date_hired", None) is None
    assert locate_field_value(page, "name", "NOT PRESENT") is None


@pytest.mark.parametrize(
    ("field", "label", "value", "value_words"),
    [
        ("name", "FULL NAME", "ROSA NGUYEN", ("ROSA", "NGUYEN")),
        ("date_of_birth", "DATE OF BIRTH", "05/10/1978", ("05/10/1978",)),
        ("license_class", "LICENSE CLASS", "A", ("A",)),
        ("state_licensed", "JURISDICTION", "LA", ("LA",)),
        ("accidents_last_5_years", "Accidents", "0", ("0",)),
        ("mvr_violations", "Moving violations", "None", ("None",)),
        ("mvr_run_date", "Run", "01/21/2026", ("01/21/2026",)),
    ],
)
def test_rectangle_matcher_uses_each_field_label_as_an_anchor(
    field: str,
    label: str,
    value: str,
    value_words: tuple[str, ...],
) -> None:
    label_words = tuple(label.split())
    words = tuple(
        PageWord(word, 0.10 + index * 0.08, 0.20, 0.17 + index * 0.08, 0.22)
        for index, word in enumerate(label_words)
    ) + tuple(
        PageWord(word, 0.31 + index * 0.08, 0.30, 0.37 + index * 0.08, 0.32)
        for index, word in enumerate(value_words)
    )

    assert locate_field_value(_matcher_page(words), field, value) == {
        "left": pytest.approx(0.31),
        "top": pytest.approx(0.30),
        "width": pytest.approx(0.06 + (len(value_words) - 1) * 0.08),
        "height": pytest.approx(0.02),
    }


def _mock_poppler(
    monkeypatch: pytest.MonkeyPatch,
    *,
    text: str = "FIRST PAGE",
    layout: str | None = _VALID_BBOX_LAYOUT,
    raw_returncode: int = 0,
    bbox_returncode: int = 0,
    render_returncode: int = 0,
) -> None:
    """Replace external Poppler processes with deterministic file outputs."""

    def fake_run(
        command: list[str],
        *,
        stdout: int,
        stderr: int,
        check: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        if command[0] == "pdftotext" and "-raw" in command:
            if raw_returncode == 0:
                Path(command[-1]).write_text(text, encoding="utf-8")
            return subprocess.CompletedProcess(command, raw_returncode)
        if command[0] == "pdftotext" and "-bbox-layout" in command:
            if bbox_returncode == 0 and layout is not None:
                Path(command[-1]).write_text(layout, encoding="utf-8")
            return subprocess.CompletedProcess(command, bbox_returncode)
        if command[0] == "pdftocairo":
            if render_returncode == 0:
                Path(f"{command[-1]}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            return subprocess.CompletedProcess(command, render_returncode)
        raise AssertionError(f"Unexpected Poppler command: {command}")

    monkeypatch.setattr(pdf_page.shutil, "which", lambda program: program)
    monkeypatch.setattr(pdf_page.subprocess, "run", fake_run)


def test_uploaded_pdf_ingestion_returns_first_page_text_layout_and_preview() -> None:
    """Ingestion must isolate the first uploaded PDF page and its geometry."""

    page = ingest_first_pdf_page(SAMPLE_PDF.read_bytes())

    assert page.text.startswith("ATTN: SAFETY OPERATIONS")
    assert "Report of Services Provided" in page.text
    assert "ROSA NGUYEN" not in page.text
    assert page.width == pytest.approx(594.96)
    assert page.height == pytest.approx(841.92)
    assert any(word.text == "ATTN:" for word in page.words)
    attn = next(word for word in page.words if word.text == "ATTN:")
    assert attn.x_min == pytest.approx(0.520485, abs=1e-6)
    assert attn.y_min == pytest.approx(0.182558, abs=1e-6)
    assert attn.x_max == pytest.approx(0.567778, abs=1e-6)
    assert attn.y_max == pytest.approx(0.195825, abs=1e-6)
    assert all(
        0.0 <= coordinate <= 1.0
        for word in page.words
        for coordinate in (word.x_min, word.y_min, word.x_max, word.y_max)
    )
    assert page.preview_png.startswith(b"\x89PNG\r\n\x1a\n")


def test_pdf_ingestion_rejects_invalid_pdf_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid input must fail at the first Poppler read boundary."""

    _mock_poppler(monkeypatch, raw_returncode=1)

    with pytest.raises(
        ValueError,
        match=r"^Could not read the first page of this PDF\.$",
    ):
        ingest_first_pdf_page(b"not a PDF")


def test_pdf_ingestion_rejects_first_page_without_embedded_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Textless first pages must not proceed to geometry or rendering."""

    _mock_poppler(monkeypatch, text="\n\f")

    with pytest.raises(
        ValueError,
        match=r"^The first page has no extractable text\.$",
    ):
        ingest_first_pdf_page(b"%PDF")


@pytest.mark.parametrize("layout", ["not XHTML", None])
def test_pdf_ingestion_rejects_malformed_or_missing_bbox_layout(
    monkeypatch: pytest.MonkeyPatch,
    layout: str | None,
) -> None:
    """Malformed or absent bbox output must not produce partial geometry."""

    _mock_poppler(monkeypatch, layout=layout)

    with pytest.raises(
        ValueError,
        match=r"^The first page has no usable layout\.$",
    ):
        ingest_first_pdf_page(b"%PDF")


def test_pdf_ingestion_rejects_render_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed page preview must return a concise rendering error."""

    _mock_poppler(monkeypatch, render_returncode=1)

    with pytest.raises(
        ValueError,
        match=r"^Could not render the first PDF page\.$",
    ):
        ingest_first_pdf_page(b"%PDF")


def test_pdf_ingestion_rejects_missing_poppler_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local deployments must receive a concise dependency error."""

    monkeypatch.setattr(pdf_page.shutil, "which", lambda _program: None)

    with pytest.raises(
        ValueError,
        match=r"^PDF ingestion tools are unavailable\.$",
    ):
        ingest_first_pdf_page(b"%PDF")


class _ButtonParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.buttons: list[dict[str, str]] = []
        self._button: dict[str, str] | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag == "button":
            self._button = {
                "id": dict(attrs).get("id") or "",
                "text": "",
            }

    def handle_data(self, data: str) -> None:
        if self._button is not None:
            self._button["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self._button is not None:
            self._button["text"] = self._button["text"].strip()
            self.buttons.append(self._button)
            self._button = None


class _FakeBonsaiClient:
    model_id = runner.DEFAULT_MODEL_ID
    endpoint = runner.DEFAULT_ENDPOINT
    request_extra_body = runner.DEFAULT_REQUEST_EXTRA_BODY

    def __init__(self, order: list[str] | None = None) -> None:
        self.prompts: list[str] = []
        self.order = order

    def generate_json(
        self,
        *,
        prompt: str,
        response_format: dict,
        max_tokens: int = 8192,
    ) -> runner.InferenceResult:
        if self.order is not None:
            self.order.append("inference")
        self.prompts.append(prompt)
        assert response_format["json_schema"]["name"] == "page_extraction"
        assert max_tokens == 8192
        return runner.InferenceResult(
            payload={
                "rows": [
                    [
                        "01/21/2026",
                        "05/10/1978",
                        "A",
                        "LA J100 200 300",
                        "01/21/2026",
                        "ROSA NGUYEN",
                        "LA",
                        None,
                        "0",
                        "None",
                    ]
                ]
            },
            attempts=1,
            prompt_tokens=420,
            completion_tokens=103,
        )


class _FakeStreamingCompletions:
    def __init__(self, order: list[str] | None = None) -> None:
        self.requests: list[dict] = []
        self.order = order

    def create(self, **kwargs):
        if self.order is not None:
            self.order.append("inference")
        self.requests.append(kwargs)
        parts = [
            '{"rows":[["01/21/2026",',
            '"05/10/1978","A","LA J100 200 300",',
            '"01/21/2026","ROSA NGUYEN","LA",null,',
            "null,null]]}",
        ]
        for part in parts:
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=part),
                    )
                ],
                usage=None,
            )
        yield SimpleNamespace(
            choices=[],
            usage=SimpleNamespace(
                prompt_tokens=382,
                completion_tokens=77,
            ),
            timings=SimpleNamespace(
                prompt_per_second=91.2,
                predicted_per_second=15.8,
            ),
        )


class _FakeStreamingBonsaiClient:
    model_id = runner.DEFAULT_MODEL_ID
    endpoint = runner.DEFAULT_ENDPOINT
    request_extra_body = runner.DEFAULT_REQUEST_EXTRA_BODY

    def __init__(self, order: list[str] | None = None) -> None:
        self.completions = _FakeStreamingCompletions(order)
        self.api = SimpleNamespace(
            chat=SimpleNamespace(completions=self.completions)
        )


def test_compact_row_decoder_emits_only_completed_field_values() -> None:
    decoder = CompactRowStreamDecoder(("name", "date_of_birth", "missing", "count"))

    assert decoder.feed('{"rows":[["RO') == []
    assert decoder.feed('SA NGUYEN","05/10/1978",nu') == [
        {"field": "name", "value": "ROSA NGUYEN"},
        {"field": "date_of_birth", "value": "05/10/1978"},
    ]
    assert decoder.feed("ll,0]]}") == [
        {"field": "missing", "value": None},
        {"field": "count", "value": 0},
    ]


def test_demo_ui_uses_plain_extraction_language_and_model_first() -> None:
    html = DEMO_HTML.read_text(encoding="utf-8")

    assert "PAGE CANDIDATE" not in html
    assert "candidate[0]" not in html
    assert "1 candidate ·" not in html
    assert "Private inference" not in html
    assert "EXTRACTED RECORD · STRICT JSON" in html
    assert "Inference · M4 Pro · 48 GB" in html
    assert '"Not found"' in html
    assert "Prompt <b" not in html
    assert "Output <b" not in html
    assert 'Prefill <b id="prefill-rate">' in html
    assert 'Decode <b id="decode-rate">' in html
    assert html.index('id="model-name"') < html.index("Prefill <b")
    assert "date_hired: [7]" not in html
    assert "if (!isMissing)" in html


def test_demo_upload_screen_does_not_offer_disk_sample_bypass() -> None:
    parser = _ButtonParser()
    parser.feed(DEMO_HTML.read_text(encoding="utf-8"))

    assert {"id": "choose", "text": "Choose PDF"} in parser.buttons
    assert not any(button["id"] == "sample" for button in parser.buttons)


def test_demo_ui_uses_uploaded_first_page_and_dynamic_rectangles() -> None:
    html = DEMO_HTML.read_text(encoding="utf-8")

    assert 'id="page-image"' in html
    assert 'id="highlight-layer"' in html
    assert 'src="/page-10.png"' not in html
    assert ".h-name" not in html
    assert "fieldHighlights" not in html
    assert 'fetch("/api/extract",' in html
    assert "preview_data_url" in html
    assert "event.rectangle" in html


def test_demo_ui_sends_uploaded_pdf_without_filename_or_browser_mime() -> None:
    """The server, rather than browser file metadata, validates uploaded PDFs."""

    from playwright.sync_api import sync_playwright

    html = DEMO_HTML.read_text(encoding="utf-8").replace(
        "</head>",
        """
  <script>
    window.__extractRequest = null;
    window.fetch = async (url, options) => {
      window.__extractRequest = {url, options};
      return {ok: false, json: async () => ({error: "Rejected by test server"})};
    };
  </script>
</head>""",
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_content(html)
        page.evaluate(
            """async () => {
              await startRun(new File(["%PDF"], "uploaded-document", {type: ""}));
            }"""
        )
        request = page.evaluate("window.__extractRequest")
        browser.close()

    assert request["url"] == "/api/extract"
    assert request["options"]["headers"]["Content-Type"] == "application/pdf"


def test_demo_ui_renders_non_a4_preview_rectangles_and_reset() -> None:
    """A preview's intrinsic dimensions keep normalized overlays aligned."""

    from playwright.sync_api import sync_playwright

    preview_data_url = (
        "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22"
        "%20width%3D%221200%22%20height%3D%22600%22%3E%3C/svg%3E"
    )
    events = [
        {
            "type": "started",
            "model_id": "mlx-community/Bonsai-27B-mlx-2bit",
            "preview_data_url": preview_data_url,
        },
        {
            "type": "field",
            "field": "name",
            "value": "Rosa",
            "rectangle": {
                "left": 0.125,
                "top": 0.25,
                "width": 0.5,
                "height": 0.125,
            },
        },
        {
            "type": "complete",
            "result": {
                "candidates": [{"name": "Rosa"}],
                "prefill_tokens_per_second": 1,
                "decode_tokens_per_second": 1,
                "elapsed_seconds": 1,
                "model_id": "mlx-community/Bonsai-27B-mlx-2bit",
            },
        },
    ]
    stream_lines = json.dumps([json.dumps(event) for event in events])
    html = DEMO_HTML.read_text(encoding="utf-8").replace(
        "</head>",
        f"""
  <script>
    const streamLines = {stream_lines};
    window.fetch = async () => ({{
      ok: true,
      body: new ReadableStream({{
        start(controller) {{
          controller.enqueue(new TextEncoder().encode(streamLines.join("\\n") + "\\n"));
          controller.close();
        }}
      }})
    }});
  </script>
</head>""",
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_content(html)
        page.evaluate(
            """async () => {
              await startRun(new File(["%PDF"], "uploaded-document", {type: ""}));
            }"""
        )
        page.wait_for_function(
            "document.getElementById('page').classList.contains('visible')"
        )
        page.wait_for_timeout(800)
        rendered = page.evaluate(
            """() => {
              const stage = document.querySelector(".document-stage").getBoundingClientRect();
              const page = document.getElementById("page").getBoundingClientRect();
              const highlight = document.querySelector(".highlight");
              const highlightRect = highlight.getBoundingClientRect();
              return {
                aspectRatio: document.getElementById("page").style.aspectRatio,
                stage: {left: stage.left, top: stage.top, right: stage.right, bottom: stage.bottom},
                page: {left: page.left, top: page.top, right: page.right, bottom: page.bottom, width: page.width, height: page.height},
                highlightRect: {left: highlightRect.left, top: highlightRect.top, right: highlightRect.right, bottom: highlightRect.bottom},
                highlight: {
                  left: highlight.style.left,
                  top: highlight.style.top,
                  width: highlight.style.width,
                  height: highlight.style.height,
                },
              };
            }"""
        )
        page.evaluate("resetRunState()")
        reset = page.evaluate(
            """() => ({
              highlights: document.querySelectorAll(".highlight").length,
              previewSource: document.getElementById("page-image").getAttribute("src"),
            })"""
        )
        browser.close()

    assert rendered["aspectRatio"] == "1200 / 600"
    assert rendered["highlight"] == {
        "left": "12.5%",
        "top": "25%",
        "width": "50%",
        "height": "12.5%",
    }
    assert rendered["page"]["left"] >= rendered["stage"]["left"] - 1
    assert rendered["page"]["top"] >= rendered["stage"]["top"] - 1
    assert rendered["page"]["right"] <= rendered["stage"]["right"] + 1
    assert rendered["page"]["bottom"] <= rendered["stage"]["bottom"] + 1
    assert rendered["page"]["width"] / rendered["page"]["height"] == pytest.approx(2, abs=0.02)
    assert rendered["highlightRect"]["left"] >= rendered["page"]["left"] - 1
    assert rendered["highlightRect"]["top"] >= rendered["page"]["top"] - 1
    assert rendered["highlightRect"]["right"] <= rendered["page"]["right"] + 1
    assert rendered["highlightRect"]["bottom"] <= rendered["page"]["bottom"] + 1
    assert rendered["highlightRect"]["left"] >= rendered["stage"]["left"] - 1
    assert rendered["highlightRect"]["top"] >= rendered["stage"]["top"] - 1
    assert rendered["highlightRect"]["right"] <= rendered["stage"]["right"] + 1
    assert rendered["highlightRect"]["bottom"] <= rendered["stage"]["bottom"] + 1
    assert reset == {"highlights": 0, "previewSource": None}


def test_compact_row_decoder_handles_comma_in_the_next_chunk() -> None:
    decoder = CompactRowStreamDecoder(("missing", "name"))

    assert decoder.feed('{"rows":[[null') == [
        {"field": "missing", "value": None}
    ]
    assert decoder.feed(',"ROSA NGUYEN"]]}') == [
        {"field": "name", "value": "ROSA NGUYEN"}
    ]


def test_streaming_service_emits_first_page_preview_and_rectangles(
    tmp_path: Path,
) -> None:
    client = _FakeStreamingBonsaiClient()
    service = DemoExtractionService(
        root=ROOT,
        output_dir=tmp_path,
        client=client,
        page_ingestor=lambda _pdf_bytes: _uploaded_page(),
        cache_clearer=lambda: None,
    )

    events = service.stream_pdf(b"arbitrary uploaded PDF bytes")
    started = next(events)
    assert started["type"] == "started"
    assert started["model_id"] == runner.DEFAULT_MODEL_ID
    assert started["page_number"] == 1
    assert started["preview_data_url"].startswith("data:image/png;base64,")
    assert client.completions.requests == []

    remaining = list(events)

    assert client.completions.requests[0]["stream"] is True
    assert client.completions.requests[0]["stream_options"] == {
        "include_usage": True
    }
    assert client.completions.requests[0]["temperature"] == 0
    field_events = [event for event in remaining if event["type"] == "field"]
    assert [(event["field"], event["value"]) for event in field_events] == [
        ("date_hired", "01/21/2026"),
        ("date_of_birth", "05/10/1978"),
        ("license_class", "A"),
        ("license_number", "LA J100 200 300"),
        ("mvr_run_date", "01/21/2026"),
        ("name", "ROSA NGUYEN"),
        ("state_licensed", "LA"),
        ("years_experienced", None),
        ("accidents_last_5_years", None),
        ("mvr_violations", None),
    ]
    name_event = next(event for event in field_events if event["field"] == "name")
    assert name_event["rectangle"] == {
        "left": pytest.approx(0.31),
        "top": pytest.approx(0.24),
        "width": pytest.approx(0.16),
        "height": pytest.approx(0.02),
    }
    assert remaining[-1]["type"] == "complete"
    result = remaining[-1]["result"]
    assert result["prompt_tokens"] == 382
    assert result["completion_tokens"] == 77
    assert result["prefill_tokens_per_second"] == 91.2
    assert result["decode_tokens_per_second"] == 15.8
    assert result["candidates"][0]["name"] == "ROSA NGUYEN"


def test_streaming_service_passes_arbitrary_pdf_bytes_to_the_ingestor(
    tmp_path: Path,
) -> None:
    received: list[bytes] = []
    client = _FakeStreamingBonsaiClient()

    def ingest(pdf_bytes: bytes) -> UploadedPage:
        received.append(pdf_bytes)
        return _uploaded_page()

    service = DemoExtractionService(
        root=ROOT,
        output_dir=tmp_path,
        client=client,
        page_ingestor=ingest,
        cache_clearer=lambda: None,
    )

    list(service.stream_pdf(b"any valid-or-invalid document bytes"))

    assert received == [b"any valid-or-invalid document bytes"]


def test_streaming_service_clears_prompt_cache_before_inference(
    tmp_path: Path,
) -> None:
    order: list[str] = []
    client = _FakeStreamingBonsaiClient(order=order)
    service = DemoExtractionService(
        root=ROOT,
        output_dir=tmp_path,
        client=client,
        page_ingestor=lambda _pdf_bytes: _uploaded_page(),
        cache_clearer=lambda: order.append("cache"),
    )

    list(service.stream_pdf(b"uploaded bytes"))

    assert order[:2] == ["cache", "inference"]


def test_prompt_cache_clear_erases_the_llama_slot(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.method
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(
        "demo.bonsai_extract.app.urllib.request.urlopen",
        fake_urlopen,
    )

    erase_llama_prompt_cache(
        "http://127.0.0.1:8080/v1",
        slot_id=0,
        timeout_seconds=3,
    )

    assert captured == {
        "url": "http://127.0.0.1:8080/slots/0?action=erase",
        "method": "POST",
        "timeout": 3,
    }


def test_extract_endpoint_rejects_cross_origin_requests() -> None:
    handler = object.__new__(DemoRequestHandler)
    handler.path = "/api/extract"
    handler.headers = Message()
    handler.headers["Host"] = "127.0.0.1:8765"
    handler.headers["Origin"] = "https://example.com"
    handler.headers["Content-Type"] = "application/pdf"
    responses: list[tuple[HTTPStatus, dict]] = []
    handler._send_json = lambda status, payload: responses.append(
        (status, payload)
    )

    handler.do_POST()

    assert responses == [
        (
            HTTPStatus.FORBIDDEN,
            {"error": "Cross-origin extraction requests are not allowed."},
        )
    ]


def test_extract_endpoint_requires_pdf_content_type() -> None:
    handler = object.__new__(DemoRequestHandler)
    handler.path = "/api/extract"
    handler.headers = Message()
    handler.headers["Host"] = "127.0.0.1:8765"
    handler.headers["Origin"] = "http://127.0.0.1:8765"
    handler.headers["Content-Type"] = "text/plain"
    responses: list[tuple[HTTPStatus, dict]] = []
    handler._send_json = lambda status, payload: responses.append(
        (status, payload)
    )

    handler.do_POST()

    assert responses == [
        (
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            {"error": "Upload an application/pdf document."},
        )
    ]


def test_non_streaming_service_clears_prompt_cache_before_inference(
    tmp_path: Path,
) -> None:
    order: list[str] = []
    client = _FakeBonsaiClient(order=order)
    service = DemoExtractionService(
        root=ROOT,
        output_dir=tmp_path,
        client=client,
        page_ingestor=lambda _pdf_bytes: _uploaded_page(),
        cache_clearer=lambda: order.append("cache"),
    )

    service.extract_pdf(b"uploaded bytes")

    assert order[:2] == ["cache", "inference"]


def test_service_uses_fresh_pdf_text_instead_of_cached_transcript(
    tmp_path: Path,
) -> None:
    client = _FakeBonsaiClient()
    calls: list[bytes] = []

    def ingest(pdf_bytes: bytes) -> UploadedPage:
        calls.append(pdf_bytes)
        page = _uploaded_page()
        return UploadedPage(
            text="FRESH PDF PAGE\nAccidents 0\nMoving violations None",
            width=page.width,
            height=page.height,
            words=page.words,
            preview_png=page.preview_png,
        )

    service = DemoExtractionService(
        root=ROOT,
        output_dir=tmp_path,
        client=client,
        page_ingestor=ingest,
        cache_clearer=lambda: None,
    )

    uploaded_bytes = b"fresh bytes"
    service.extract_pdf(uploaded_bytes)

    assert calls == [uploaded_bytes]
    assert "FRESH PDF PAGE" in client.prompts[0]
    assert "MOTOR VEHICLE RECORDS BUREAU" not in client.prompts[0]


def test_first_page_runs_through_existing_page_pipeline(tmp_path: Path) -> None:
    client = _FakeBonsaiClient()
    service = DemoExtractionService(
        root=ROOT,
        output_dir=tmp_path,
        client=client,
        page_ingestor=lambda _pdf_bytes: _uploaded_page(),
        cache_clearer=lambda: None,
    )

    result = service.extract_pdf(b"uploaded bytes")

    assert len(client.prompts) == 1
    assert "# Page 1" in client.prompts[0]
    assert "ROSA NGUYEN" in client.prompts[0]
    assert "05/10/1978" in client.prompts[0]
    assert "# Page 2" not in client.prompts[0]
    assert result["sample"] == "driver_mvr_packet_001"
    assert result["page_number"] == 1
    assert result["candidates"] == [
        {
            "date_hired": "01/21/2026",
            "date_of_birth": "05/10/1978",
            "license_class": "A",
            "license_number": "LA J100 200 300",
            "mvr_run_date": "01/21/2026",
            "name": "ROSA NGUYEN",
            "state_licensed": "LA",
            "accidents_last_5_years": "0",
            "mvr_violations": "None",
        }
    ]
    assert result["model_id"] == runner.DEFAULT_MODEL_ID
    assert result["endpoint"] == runner.DEFAULT_ENDPOINT
    assert result["prompt_tokens"] == 420
    assert result["completion_tokens"] == 103
    assert result["attempts"] == 1
    assert result["elapsed_seconds"] >= 0

    checkpoint = (
        tmp_path
        / "pages"
        / "driver_mvr_packet_001"
        / "page_0001.json"
    )
    assert checkpoint.is_file()
