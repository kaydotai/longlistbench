"""First-page PDF ingestion for the local Bonsai demo."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
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


def locate_field_value(
    page: UploadedPage,
    field: str,
    value: object,
) -> dict[str, float] | None:
    """Locate an extracted value using its field label as a semantic anchor."""

    if value is None or field not in FIELD_LABELS:
        return None

    value_terms = _normalized_terms(str(value))
    if not value_terms:
        return None

    value_matches = _find_word_sequences(page.words, value_terms)
    if not value_matches:
        return None

    label_matches = [
        match
        for label in FIELD_LABELS[field]
        for match in _find_word_sequences(page.words, _normalized_terms(label))
    ]
    if not label_matches:
        return None

    value_words = min(
        value_matches,
        key=lambda candidate: min(
            _anchor_distance_score(candidate, label)
            for label in label_matches
        ),
    )
    left = min(word.x_min for word in value_words)
    top = min(word.y_min for word in value_words)
    right = max(word.x_max for word in value_words)
    bottom = max(word.y_max for word in value_words)
    return {
        "left": max(0.0, min(left, 1.0)),
        "top": max(0.0, min(top, 1.0)),
        "width": max(0.0, min(right, 1.0) - max(0.0, min(left, 1.0))),
        "height": max(0.0, min(bottom, 1.0) - max(0.0, min(top, 1.0))),
    }


def _normalized_terms(text: str) -> tuple[str, ...]:
    normalized = _normalized_text(text)
    return tuple(normalized.split(" ")) if normalized else ()


def _normalized_text(text: str) -> str:
    return " ".join(text.split()).casefold()


def _find_word_sequences(
    words: tuple[PageWord, ...],
    terms: tuple[str, ...],
) -> list[tuple[PageWord, ...]]:
    if not terms:
        return []
    normalized_words = tuple(_normalized_text(word.text) for word in words)
    return [
        words[index : index + len(terms)]
        for index in range(len(words) - len(terms) + 1)
        if normalized_words[index : index + len(terms)] == terms
    ]


def _anchor_distance_score(
    value_words: tuple[PageWord, ...],
    label_words: tuple[PageWord, ...],
) -> tuple[bool, float]:
    value_center = _word_sequence_center(value_words)
    label_center = _word_sequence_center(label_words)
    is_below_or_right = (
        value_center[1] >= label_center[1]
        or value_center[0] >= label_center[0]
    )
    return (
        not is_below_or_right,
        hypot(
            value_center[0] - label_center[0],
            value_center[1] - label_center[1],
        ),
    )


def _word_sequence_center(words: tuple[PageWord, ...]) -> tuple[float, float]:
    return (
        (min(word.x_min for word in words) + max(word.x_max for word in words)) / 2,
        (min(word.y_min for word in words) + max(word.y_max for word in words)) / 2,
    )


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
        if width <= 0 or height <= 0:
            raise ValueError("The first page has no usable layout.")
        words = tuple(
            PageWord(
                text="".join(word.itertext()).strip(),
                x_min=float(word.attrib["xMin"]) / width,
                y_min=float(word.attrib["yMin"]) / height,
                x_max=float(word.attrib["xMax"]) / width,
                y_max=float(word.attrib["yMax"]) / height,
            )
            for word in _elements_named(page, "word")
            if "".join(word.itertext()).strip()
        )
    except (
        ElementTree.ParseError,
        KeyError,
        OSError,
        StopIteration,
        ValueError,
    ) as exc:
        raise ValueError("The first page has no usable layout.") from exc
    if not words:
        raise ValueError("The first page has no usable layout.")
    return width, height, words


def _elements_named(root: ElementTree.Element, name: str):
    for element in root.iter():
        if element.tag.rsplit("}", maxsplit=1)[-1] == name:
            yield element
