from __future__ import annotations

from email.message import Message
from html.parser import HTMLParser
from http import HTTPStatus
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from benchmarks import run_bonsai_page_evaluation as runner
from demo.bonsai_extract.app import (
    CompactRowStreamDecoder,
    DemoExtractionService,
    DemoRequestHandler,
    UnsupportedDocumentError,
    erase_llama_prompt_cache,
    extract_pdf_page_text,
)
from demo.bonsai_extract import pdf_page
from demo.bonsai_extract.pdf_page import ingest_first_pdf_page


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


def _sample_page_text(_pdf_bytes: bytes, page_number: int) -> str:
    assert page_number == 10
    return SAMPLE_PAGE_TEXT


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


def test_demo_highlights_use_normalized_pdf_text_coordinates() -> None:
    html = DEMO_HTML.read_text(encoding="utf-8")

    assert "pdftotext -bbox · page 10 · 594.96 × 841.92 pt" in html
    assert "aspect-ratio: 594.96 / 841.92;" in html
    assert ".h-name { left: 9.71%; top: 28.30%;" in html
    assert ".h-license { left: 30.86%; top: 40.06%;" in html
    assert ".h-state { left: 9.71%; top: 40.06%;" in html
    assert ".h-accidents { left: 34.40%; top: 50.49%;" in html
    assert ".h-violations { left: 34.40%; top: 54.76%;" in html


def test_compact_row_decoder_handles_comma_in_the_next_chunk() -> None:
    decoder = CompactRowStreamDecoder(("missing", "name"))

    assert decoder.feed('{"rows":[[null') == [
        {"field": "missing", "value": None}
    ]
    assert decoder.feed(',"ROSA NGUYEN"]]}') == [
        {"field": "name", "value": "ROSA NGUYEN"}
    ]


def test_streaming_service_emits_fields_before_the_completed_result(
    tmp_path: Path,
) -> None:
    client = _FakeStreamingBonsaiClient()
    service = DemoExtractionService(
        root=ROOT,
        output_dir=tmp_path,
        client=client,
        page_text_extractor=_sample_page_text,
        cache_clearer=lambda: None,
    )

    events = service.stream_pdf(SAMPLE_PDF.read_bytes(), page_number=10)
    assert next(events) == {
        "type": "started",
        "model_id": runner.DEFAULT_MODEL_ID,
        "page_number": 10,
        "source": "embedded_pdf_text",
    }
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
    assert remaining[-1]["type"] == "complete"
    result = remaining[-1]["result"]
    assert result["prompt_tokens"] == 382
    assert result["completion_tokens"] == 77
    assert result["prefill_tokens_per_second"] == 91.2
    assert result["decode_tokens_per_second"] == 15.8
    assert result["candidates"][0]["name"] == "ROSA NGUYEN"


def test_streaming_service_clears_prompt_cache_before_inference(
    tmp_path: Path,
) -> None:
    order: list[str] = []
    client = _FakeStreamingBonsaiClient(order=order)
    service = DemoExtractionService(
        root=ROOT,
        output_dir=tmp_path,
        client=client,
        page_text_extractor=_sample_page_text,
        cache_clearer=lambda: order.append("cache"),
    )

    list(service.stream_pdf(SAMPLE_PDF.read_bytes(), page_number=10))

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
    handler.path = "/api/extract?page=10"
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
    handler.path = "/api/extract?page=10"
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
        page_text_extractor=_sample_page_text,
        cache_clearer=lambda: order.append("cache"),
    )

    service.extract_pdf(SAMPLE_PDF.read_bytes(), page_number=10)

    assert order[:2] == ["cache", "inference"]


def test_exact_bundled_pdf_is_required_before_inference(tmp_path: Path) -> None:
    order: list[str] = []
    client = _FakeBonsaiClient(order=order)
    service = DemoExtractionService(
        root=ROOT,
        output_dir=tmp_path,
        client=client,
        cache_clearer=lambda: order.append("cache"),
    )

    with pytest.raises(UnsupportedDocumentError, match="bundled demo PDF"):
        service.extract_pdf(SAMPLE_PDF.read_bytes() + b"changed", page_number=10)

    assert client.prompts == []
    assert order == []


@pytest.mark.skipif(
    shutil.which("pdftotext") is None,
    reason="Poppler is a documented runtime prerequisite",
)
def test_pdf_page_text_is_extracted_from_the_uploaded_document() -> None:
    page_text = extract_pdf_page_text(
        SAMPLE_PDF.read_bytes(),
        page_number=10,
    )

    assert "Certified Employer Driving Record" in page_text
    assert "ROSA NGUYEN" in page_text
    assert "Run 01/21/2026" in page_text
    assert "DATE OF BIRTH\n05/10/1978" in page_text
    assert "Accidents 0" in page_text
    assert "Moving violations None" in page_text


def test_service_uses_fresh_pdf_text_instead_of_cached_transcript(
    tmp_path: Path,
) -> None:
    client = _FakeBonsaiClient()
    calls: list[tuple[bytes, int]] = []

    def extract_page(pdf_bytes: bytes, page_number: int) -> str:
        calls.append((pdf_bytes, page_number))
        return "FRESH PDF PAGE\nAccidents 0\nMoving violations None"

    service = DemoExtractionService(
        root=ROOT,
        output_dir=tmp_path,
        client=client,
        page_text_extractor=extract_page,
        cache_clearer=lambda: None,
    )

    service.extract_pdf(SAMPLE_PDF.read_bytes(), page_number=10)

    assert calls == [(SAMPLE_PDF.read_bytes(), 10)]
    assert "FRESH PDF PAGE" in client.prompts[0]
    assert "MOTOR VEHICLE RECORDS BUREAU" not in client.prompts[0]


def test_page_10_runs_through_existing_page_pipeline(tmp_path: Path) -> None:
    client = _FakeBonsaiClient()
    service = DemoExtractionService(
        root=ROOT,
        output_dir=tmp_path,
        client=client,
        page_text_extractor=_sample_page_text,
        cache_clearer=lambda: None,
    )

    result = service.extract_pdf(SAMPLE_PDF.read_bytes(), page_number=10)

    assert len(client.prompts) == 1
    assert "# Page 10" in client.prompts[0]
    assert "ROSA NGUYEN" in client.prompts[0]
    assert "05/10/1978" in client.prompts[0]
    assert "# Page 11" not in client.prompts[0]
    assert result["sample"] == "driver_mvr_packet_001"
    assert result["page_number"] == 10
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
        / "page_0010.json"
    )
    assert checkpoint.is_file()


def test_unsupported_page_is_rejected_without_inference(tmp_path: Path) -> None:
    client = _FakeBonsaiClient()
    service = DemoExtractionService(
        root=ROOT,
        output_dir=tmp_path,
        client=client,
        cache_clearer=lambda: None,
    )

    with pytest.raises(ValueError, match="page 99"):
        service.extract_pdf(SAMPLE_PDF.read_bytes(), page_number=99)

    assert client.prompts == []
