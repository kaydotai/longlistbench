"""First-page PDF ingestion for the local Bonsai demo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ElementTree


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
    """Extract text, word geometry, and a preview from an uploaded PDF's first page."""

    pdftotext = shutil.which("pdftotext")
    pdftocairo = shutil.which("pdftocairo")
    if pdftotext is None or pdftocairo is None:
        raise ValueError("PDF ingestion tools are unavailable.")

    with TemporaryDirectory() as temporary_directory:
        directory = Path(temporary_directory)
        pdf_path = directory / "upload.pdf"
        text_path = directory / "page.txt"
        layout_path = directory / "page.xhtml"
        preview_root = directory / "preview"
        preview_path = directory / "preview.png"
        pdf_path.write_bytes(pdf_bytes)

        _run_poppler(
            [
                pdftotext,
                "-f",
                "1",
                "-l",
                "1",
                "-raw",
                str(pdf_path),
                str(text_path),
            ],
            "Could not read the first page of this PDF.",
        )
        text = text_path.read_text(encoding="utf-8", errors="replace").replace(
            "\f", ""
        ).strip()
        if not text:
            raise ValueError("The first page has no extractable text.")

        _run_poppler(
            [
                pdftotext,
                "-f",
                "1",
                "-l",
                "1",
                "-bbox-layout",
                str(pdf_path),
                str(layout_path),
            ],
            "Could not read the first-page layout.",
        )
        width, height, words = _parse_layout(layout_path)

        _run_poppler(
            [
                pdftocairo,
                "-f",
                "1",
                "-l",
                "1",
                "-png",
                "-singlefile",
                "-r",
                "150",
                str(pdf_path),
                str(preview_root),
            ],
            "Could not render the first PDF page.",
        )
        if not preview_path.is_file() or not preview_path.read_bytes():
            raise ValueError("Could not render the first PDF page.")

        return UploadedPage(
            text=text,
            width=width,
            height=height,
            words=words,
            preview_png=preview_path.read_bytes(),
        )


def _run_poppler(command: list[str], message: str) -> None:
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise ValueError("PDF ingestion tools are unavailable.") from exc
    if completed.returncode != 0:
        raise ValueError(message)


def _parse_layout(layout_path: Path) -> tuple[float, float, tuple[PageWord, ...]]:
    try:
        root = ElementTree.parse(layout_path).getroot()
        page = next(_elements_named(root, "page"))
        width = float(page.attrib["width"])
        height = float(page.attrib["height"])
        words = tuple(
            PageWord(
                text="".join(word.itertext()).strip(),
                x_min=float(word.attrib["xMin"]),
                y_min=float(word.attrib["yMin"]),
                x_max=float(word.attrib["xMax"]),
                y_max=float(word.attrib["yMax"]),
            )
            for word in _elements_named(page, "word")
            if "".join(word.itertext()).strip()
        )
    except (
        ElementTree.ParseError,
        KeyError,
        StopIteration,
        ValueError,
    ) as exc:
        raise ValueError("The first page has no usable layout.") from exc
    if width <= 0 or height <= 0 or not words:
        raise ValueError("The first page has no usable layout.")
    return width, height, words


def _elements_named(root: ElementTree.Element, name: str):
    for element in root.iter():
        if element.tag.rsplit("}", maxsplit=1)[-1] == name:
            yield element
