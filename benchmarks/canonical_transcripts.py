#!/usr/bin/env python3
"""Generate canonical transcript Markdown from rendered benchmark HTML."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


_VOID_TAGS = {"br", "meta", "img", "input", "link", "hr"}


@dataclass
class HtmlNode:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["HtmlNode | str"] = field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return {c for c in self.attrs.get("class", "").split() if c}


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode(tag="document")
        self._stack: list[HtmlNode] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = HtmlNode(tag=tag, attrs={k: (v or "") for k, v in attrs})
        self._stack[-1].children.append(node)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = HtmlNode(tag=tag, attrs={k: (v or "") for k, v in attrs})
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        for idx in range(len(self._stack) - 1, 0, -1):
            if self._stack[idx].tag == tag:
                del self._stack[idx:]
                break

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].children.append(data)


def _iter_child_nodes(node: HtmlNode) -> Iterable[HtmlNode]:
    for child in node.children:
        if isinstance(child, HtmlNode):
            yield child


def _find_first(node: HtmlNode, *, tag: str | None = None, class_name: str | None = None) -> HtmlNode | None:
    for child in _iter_child_nodes(node):
        if (tag is None or child.tag == tag) and (class_name is None or class_name in child.classes):
            return child
        found = _find_first(child, tag=tag, class_name=class_name)
        if found is not None:
            return found
    return None


def _find_all(node: HtmlNode, *, tag: str | None = None, class_name: str | None = None) -> list[HtmlNode]:
    out: list[HtmlNode] = []
    for child in _iter_child_nodes(node):
        if (tag is None or child.tag == tag) and (class_name is None or class_name in child.classes):
            out.append(child)
        out.extend(_find_all(child, tag=tag, class_name=class_name))
    return out


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


def _join_tokens(tokens: list[str]) -> str:
    out: list[str] = []
    for token in tokens:
        if token == "\n":
            if out and out[-1].endswith(" "):
                out[-1] = out[-1].rstrip()
            if not out or out[-1] != "\n":
                out.append("\n")
            continue

        token = token.strip()
        if not token:
            continue

        if out and out[-1] not in {"\n"} and not out[-1].endswith((" ", "(", "/", "-")):
            if not token.startswith((")", ",", ".", ":", ";", "?", "!")):
                out.append(" ")
        out.append(token)

    return "".join(out)


def _collect_text(node: HtmlNode, *, br_newline: bool = False) -> str:
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
            continue
        if child.tag == "br":
            parts.append("\n" if br_newline else " ")
            continue
        parts.append(_collect_text(child, br_newline=br_newline))
    text = _join_tokens(parts)
    if br_newline:
        lines = [_normalize_ws(line) for line in text.splitlines()]
        return "\n".join(line for line in lines if line)
    return _normalize_ws(text)


def _markdown_table(table: HtmlNode) -> str:
    rows: list[list[str]] = []
    for tr in _find_all(table, tag="tr"):
        cells = [child for child in _iter_child_nodes(tr) if child.tag in {"th", "td"}]
        if not cells:
            continue
        row = []
        for cell in cells:
            value = _collect_text(cell, br_newline=True).replace("\n", " <br> ")
            value = value.replace("|", "\\|")
            row.append(value)
        rows.append(row)

    if not rows:
        return ""

    header = rows[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * len(header)) + " |",
    ]
    for row in rows[1:]:
        padded = row + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(padded[: len(header)]) + " |")
    return "\n".join(lines)


def _render_header(node: HtmlNode) -> str:
    lines: list[str] = []
    for div in _find_all(node, tag="div"):
        if any(child.tag == "div" for child in _iter_child_nodes(div)):
            continue
        text = _collect_text(div, br_newline=True)
        if text and text not in lines:
            lines.append(text)
    return "\n".join(lines)


def _render_incident_section(node: HtmlNode) -> str:
    lines: list[str] = []
    header = _find_first(node, class_name="incident-header")
    if header is not None:
        lines.append(_collect_text(header))

    details = _find_first(node, class_name="incident-details")
    if details is not None:
        for child in _iter_child_nodes(details):
            text = _collect_text(child, br_newline=True)
            if text:
                lines.extend(line for line in text.splitlines() if line)

    for table in [child for child in _iter_child_nodes(node) if child.tag == "table"]:
        table_md = _markdown_table(table)
        if table_md:
            lines.append(table_md)

    return "\n".join(lines)


def _render_table_section(node: HtmlNode) -> str:
    tables = [child for child in _iter_child_nodes(node) if child.tag == "table"]
    blocks = [_markdown_table(table) for table in tables]
    return "\n\n".join(block for block in blocks if block)


def _render_grand_total(node: HtmlNode) -> str:
    lines: list[str] = []
    for child in _iter_child_nodes(node):
        if child.tag == "table":
            table_md = _markdown_table(child)
            if table_md:
                lines.append(table_md)
            continue
        text = _collect_text(child, br_newline=True)
        if text:
            lines.extend(line for line in text.splitlines() if line)
    return "\n".join(lines)


def _render_simple_text(node: HtmlNode) -> str:
    return _collect_text(node, br_newline=True)


def _iter_blocks(node: HtmlNode) -> Iterable[tuple[str, str]]:
    for child in _iter_child_nodes(node):
        if child.tag in {"style", "script"}:
            continue
        if "page-break" in child.classes:
            yield ("page_break", "")
            continue
        if "header" in child.classes:
            yield ("block", _render_header(child))
            continue
        if "incident-section" in child.classes:
            yield ("block", _render_incident_section(child))
            continue
        if "table-section" in child.classes:
            yield ("block", _render_table_section(child))
            continue
        if "grand-total-section" in child.classes:
            yield ("block", _render_grand_total(child))
            continue
        if "footer" in child.classes:
            yield ("block", _render_simple_text(child))
            continue
        yield from _iter_blocks(child)


def generate_canonical_markdown(html_text: str) -> str:
    parser = _TreeBuilder()
    parser.feed(html_text)
    body = _find_first(parser.root, tag="body")
    if body is None:
        return ""

    pages: list[list[str]] = [[]]
    for kind, block in _iter_blocks(body):
        if kind == "page_break":
            if pages[-1]:
                pages.append([])
            continue
        block = block.strip()
        if block:
            pages[-1].append(block)

    if not pages[-1]:
        pages = pages[:-1] or [[]]

    out_parts: list[str] = []
    for idx, page_blocks in enumerate(pages, start=1):
        out_parts.append(f"# Page {idx}")
        out_parts.append("")
        if page_blocks:
            out_parts.append("\n\n".join(page_blocks))
            out_parts.append("")

    return "\n".join(out_parts).rstrip() + "\n"


def generate_canonical_markdown_from_html(html_path: Path) -> str:
    return generate_canonical_markdown(html_path.read_text(encoding="utf-8"))


def write_canonical_markdown_from_html(html_path: Path, output_path: Path) -> str:
    markdown = generate_canonical_markdown_from_html(html_path)
    output_path.write_text(markdown, encoding="utf-8")
    return markdown
