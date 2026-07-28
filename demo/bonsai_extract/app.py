#!/usr/bin/env python3
"""Serve the local Bonsai document-extraction demo."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from collections.abc import Iterator
from typing import Any, Callable

from benchmarks import run_bonsai_page_evaluation as runner
from demo.bonsai_extract.pdf_page import (
    UploadedPage,
    ingest_first_pdf_page,
    locate_field_value,
)


ROOT = Path(__file__).resolve().parents[2]
SAMPLE_ID = "driver_mvr_packet_001"
SAMPLE_TEMPLATE = "driver_mvr_request_and_roster"
INDEX_HTML = Path(__file__).with_name("index.html")
DEFAULT_OUTPUT_DIR = ROOT / "demo_runs" / "bonsai_extract"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def erase_llama_prompt_cache(
    endpoint: str,
    slot_id: int = 0,
    timeout_seconds: float = 5,
) -> None:
    """Erase one llama.cpp slot before measuring a fresh prefill."""

    parsed = urllib.parse.urlsplit(endpoint)
    origin = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, "", "", "")
    ).rstrip("/")
    request = urllib.request.Request(
        f"{origin}/slots/{slot_id}?action=erase",
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds):
            pass
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError(
            "Could not clear the local llama.cpp prompt cache."
        ) from exc


class CompactRowStreamDecoder:
    """Decode completed values from the first compact JSON row incrementally."""

    _ROW_START = re.compile(r'"rows"\s*:\s*\[\s*\[')

    def __init__(self, fields: tuple[str, ...]) -> None:
        self.fields = fields
        self.buffer = ""
        self.position: int | None = None
        self.field_index = 0
        self.needs_separator = False
        self.decoder = json.JSONDecoder()

    def feed(self, content: str) -> list[dict[str, Any]]:
        self.buffer += content
        if self.position is None:
            match = self._ROW_START.search(self.buffer)
            if match is None:
                return []
            self.position = match.end()

        events: list[dict[str, Any]] = []
        while self.field_index < len(self.fields):
            assert self.position is not None
            while (
                self.position < len(self.buffer)
                and self.buffer[self.position].isspace()
            ):
                self.position += 1
            if self.position >= len(self.buffer):
                break
            if self.needs_separator:
                if self.buffer[self.position] != ",":
                    break
                self.position += 1
                self.needs_separator = False
                while (
                    self.position < len(self.buffer)
                    and self.buffer[self.position].isspace()
                ):
                    self.position += 1
                if self.position >= len(self.buffer):
                    break
            try:
                value, end = self.decoder.raw_decode(
                    self.buffer,
                    self.position,
                )
            except json.JSONDecodeError:
                break
            events.append(
                {
                    "field": self.fields[self.field_index],
                    "value": value,
                }
            )
            self.field_index += 1
            self.position = end
            self.needs_separator = self.field_index < len(self.fields)
        return events


class DemoExtractionService:
    """Ingest an uploaded first page and execute the page pipeline."""

    def __init__(
        self,
        *,
        root: Path = ROOT,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        client: Any | None = None,
        page_ingestor: Callable[[bytes], UploadedPage] = ingest_first_pdf_page,
        cache_clearer: Callable[[], None] | None = None,
    ) -> None:
        self.root = root
        self.output_dir = output_dir
        self.page_ingestor = page_ingestor
        self.client = client or runner.BonsaiClient(
            endpoint=runner.DEFAULT_ENDPOINT,
            model_id=runner.DEFAULT_MODEL_ID,
            max_attempts=1,
        )
        self.cache_clearer = cache_clearer
        if self.cache_clearer is None:
            self.cache_clearer = lambda: erase_llama_prompt_cache(
                self.client.endpoint
            )

    def extract_pdf(self, pdf_bytes: bytes) -> dict[str, Any]:
        uploaded_page = self.page_ingestor(pdf_bytes)
        page = self._runner_page(uploaded_page)
        self.cache_clearer()
        checkpoints = runner.extract_pages(
            sample=SAMPLE_ID,
            pages=[page],
            contract=runner.contract_for_template(SAMPLE_TEMPLATE),
            client=self.client,
            output_dir=self.output_dir,
            resume=False,
            validation_attempts=1,
        )
        return self._browser_result(checkpoints[0])

    def stream_pdf(self, pdf_bytes: bytes) -> Iterator[dict[str, Any]]:
        uploaded_page = self.page_ingestor(pdf_bytes)
        page = self._runner_page(uploaded_page)
        self.cache_clearer()
        return self._stream_page(page, uploaded_page)

    @staticmethod
    def _runner_page(uploaded_page: UploadedPage) -> runner.Page:
        return runner.Page(
            number=1,
            text=f"# Page 1\n\n{uploaded_page.text}\n",
        )

    def _stream_page(
        self,
        page: runner.Page,
        uploaded_page: UploadedPage,
    ) -> Iterator[dict[str, Any]]:
        yield {
            "type": "started",
            "model_id": self.client.model_id,
            "page_number": page.number,
            "preview_data_url": (
                "data:image/png;base64,"
                + base64.b64encode(uploaded_page.preview_png).decode("ascii")
            ),
        }

        contract = runner.contract_for_template(SAMPLE_TEMPLATE)
        fields = tuple(
            field
            for field in contract.required_fields["record"]
            if field != "record_type"
        )
        prompt = runner.build_page_prompt(contract, page)
        response_format = runner.page_response_format(contract)
        request: dict[str, Any] = {
            "model": self.client.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": response_format,
            "max_tokens": 8192,
            "temperature": 0,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self.client.request_extra_body is not None:
            request["extra_body"] = self.client.request_extra_body

        started = time.monotonic()
        decoder = CompactRowStreamDecoder(fields)
        content_parts: list[str] = []
        prompt_tokens = 0
        completion_tokens = 0
        prefill_tokens_per_second = 0.0
        decode_tokens_per_second = 0.0
        stream = self.client.api.chat.completions.create(**request)
        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                prompt_tokens = int(
                    getattr(usage, "prompt_tokens", 0) or 0
                )
                completion_tokens = int(
                    getattr(usage, "completion_tokens", 0) or 0
                )
            timings = getattr(chunk, "timings", None)
            if timings is None:
                timings = (getattr(chunk, "model_extra", None) or {}).get(
                    "timings"
                )
            if timings is not None:
                if isinstance(timings, dict):
                    prefill_tokens_per_second = float(
                        timings.get("prompt_per_second", 0) or 0
                    )
                    decode_tokens_per_second = float(
                        timings.get("predicted_per_second", 0) or 0
                    )
                else:
                    prefill_tokens_per_second = float(
                        getattr(timings, "prompt_per_second", 0) or 0
                    )
                    decode_tokens_per_second = float(
                        getattr(timings, "predicted_per_second", 0) or 0
                    )
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            content = getattr(choices[0].delta, "content", None)
            if not content:
                continue
            content_parts.append(content)
            for field_event in decoder.feed(content):
                event = {"type": "field", **field_event}
                if field_event["value"] is not None:
                    rectangle = locate_field_value(
                        uploaded_page,
                        field_event["field"],
                        field_event["value"],
                    )
                    if rectangle is not None:
                        event["rectangle"] = rectangle
                yield event

        payload = json.loads("".join(content_parts))
        candidates = runner._validate_candidates(payload, contract)
        elapsed_seconds = time.monotonic() - started
        checkpoint = runner.build_page_checkpoint(
            sample=SAMPLE_ID,
            page=page,
            candidates=candidates,
            attempts=1,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            request_fingerprint=runner._request_fingerprint(
                client=self.client,
                prompt=prompt,
                response_format=response_format,
            ),
            model_id=self.client.model_id,
            endpoint=self.client.endpoint,
        )
        checkpoint["elapsed_seconds"] = elapsed_seconds
        checkpoint["prefill_tokens_per_second"] = prefill_tokens_per_second
        checkpoint["decode_tokens_per_second"] = decode_tokens_per_second
        checkpoint_path = (
            self.output_dir
            / "pages"
            / SAMPLE_ID
            / f"page_{page.number:04d}.json"
        )
        runner._atomic_write_json(checkpoint_path, checkpoint)
        runner.append_event(
            self.output_dir,
            {
                "type": "page_complete",
                "sample": SAMPLE_ID,
                "page_number": page.number,
                "candidate_count": len(candidates),
                "attempts": 1,
                "checkpoint": checkpoint_path.relative_to(
                    self.output_dir
                ).as_posix(),
                "streamed": True,
            },
        )
        yield {
            "type": "complete",
            "result": self._browser_result(checkpoint),
        }

    @staticmethod
    def _browser_result(
        checkpoint: dict[str, Any],
    ) -> dict[str, Any]:
        elapsed_seconds = float(checkpoint.get("elapsed_seconds") or 0)
        completion_tokens = int(checkpoint.get("completion_tokens") or 0)
        result = dict(checkpoint)
        result["output_tokens_per_second"] = (
            completion_tokens / elapsed_seconds if elapsed_seconds > 0 else 0
        )
        result.setdefault("prefill_tokens_per_second", 0)
        result.setdefault(
            "decode_tokens_per_second",
            result["output_tokens_per_second"],
        )
        result["hardware"] = {
            "private": True,
            "device": "M4 Pro",
            "memory_gb": 48,
        }
        return result


class DemoRequestHandler(BaseHTTPRequestHandler):
    """HTTP interface for the browser demo."""

    server_version = "BonsaiExtractDemo/1.0"

    @property
    def extraction_service(self) -> DemoExtractionService:
        return self.server.extraction_service  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        route = urllib.parse.urlparse(self.path).path
        if route == "/":
            self._send_file(INDEX_HTML, "text/html; charset=utf-8")
        elif route == "/api/health":
            self._send_health()
        else:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "Not found."},
            )

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/extract":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return

        origin = self.headers.get("Origin")
        expected_origin = f"http://{self.headers.get('Host', '')}"
        if origin and origin != expected_origin:
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"error": "Cross-origin extraction requests are not allowed."},
            )
            return

        content_type = self.headers.get("Content-Type", "")
        if content_type.split(";", 1)[0].strip().lower() != "application/pdf":
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"error": "Upload an application/pdf document."},
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Send a PDF in the request body."},
            )
            return
        if content_length > MAX_UPLOAD_BYTES:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": "The PDF is too large for this demo."},
            )
            return

        pdf_bytes = self.rfile.read(content_length)
        try:
            events = self.extraction_service.stream_pdf(pdf_bytes)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self.log_error("inference failed: %s", exc)
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {
                    "error": (
                        "Local Bonsai inference failed. Confirm llama-server "
                        "is healthy on 127.0.0.1:8080."
                    )
                },
            )
        else:
            self.send_response(HTTPStatus.OK)
            self.send_header(
                "Content-Type",
                "application/x-ndjson; charset=utf-8",
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                for event in events:
                    body = (
                        json.dumps(event, ensure_ascii=False) + "\n"
                    ).encode("utf-8")
                    self.wfile.write(body)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                self.log_message("client disconnected during inference")
            except Exception as exc:
                self.log_error("streaming inference failed: %s", exc)
                error = {
                    "type": "error",
                    "error": (
                        "Local Bonsai inference failed. Confirm llama-server "
                        "is healthy on 127.0.0.1:8080."
                    ),
                }
                try:
                    self.wfile.write(
                        (json.dumps(error) + "\n").encode("utf-8")
                    )
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

    def _send_health(self) -> None:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8080/health",
                timeout=1,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            OSError,
            json.JSONDecodeError,
            urllib.error.URLError,
        ) as exc:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ready": False, "error": str(exc)},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            {"ready": True, "model_id": runner.DEFAULT_MODEL_ID, "upstream": payload},
        )

    def _send_file(self, path: Path, content_type: str | None = None) -> None:
        if not path.is_file():
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": f"Missing demo asset: {path.name}"},
            )
            return
        body = path.read_bytes()
        guessed_type = mimetypes.guess_type(path.name)[0]
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type",
            content_type or guessed_type or "application/octet-stream",
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: HTTPStatus, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[demo] {self.address_string()} {format % args}")


class DemoHTTPServer(ThreadingHTTPServer):
    """HTTP server carrying the shared extraction service."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        extraction_service: DemoExtractionService,
    ) -> None:
        super().__init__(server_address, DemoRequestHandler)
        self.extraction_service = extraction_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    service = DemoExtractionService(output_dir=args.output_dir)
    server = DemoHTTPServer((args.host, args.port), service)
    print(
        f"Local Bonsai extraction demo: http://{args.host}:{args.port}/",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
