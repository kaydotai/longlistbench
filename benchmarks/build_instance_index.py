#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from html import escape
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    from pdf2image import pdfinfo_from_path
except ImportError:
    pdfinfo_from_path = None


def _get_pdf_page_count(pdf_path: Path) -> int | None:
    if not pdf_path.exists():
        return None

    if pdfinfo_from_path is None:
        return None

    try:
        info = pdfinfo_from_path(str(pdf_path))
    except Exception:
        return None

    try:
        return int(info.get("Pages"))
    except Exception:
        return None


def _file_size_bytes(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return None


def build_instance_index(dataset_dir: Path) -> dict[str, Any]:
    metadata_path = dataset_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    out_instances: list[dict[str, Any]] = []

    for inst in metadata.get("instances", []):
        instance_id = inst.get("id")
        if not instance_id:
            continue

        pdf_path = dataset_dir / f"{instance_id}.pdf"
        html_path = dataset_dir / f"{instance_id}.html"
        json_path = dataset_dir / f"{instance_id}.json"
        ocr_md_path = dataset_dir / f"{instance_id}_ocr.md"

        out_instances.append(
            {
                "id": instance_id,
                "difficulty": inst.get("difficulty"),
                "format": inst.get("format"),
                "problems": inst.get("problems", []),
                "num_claims": inst.get("num_claims"),
                "pages_estimate": inst.get("pages_estimate"),
                "seed": inst.get("seed"),
                "files": {
                    "pdf": str(pdf_path.name),
                    "html": str(html_path.name),
                    "ground_truth": str(json_path.name),
                    "ocr_md": str(ocr_md_path.name),
                    "pdf_exists": pdf_path.exists(),
                    "html_exists": html_path.exists(),
                    "ground_truth_exists": json_path.exists(),
                    "ocr_md_exists": ocr_md_path.exists(),
                    "pdf_size_bytes": _file_size_bytes(pdf_path),
                    "html_size_bytes": _file_size_bytes(html_path),
                    "json_size_bytes": _file_size_bytes(json_path),
                    "ocr_md_size_bytes": _file_size_bytes(ocr_md_path),
                    "pdf_pages": _get_pdf_page_count(pdf_path),
                },
            }
        )

    return {
        "built_at": datetime.now().isoformat(),
        "dataset_dir": str(dataset_dir),
        "source_metadata": str(metadata_path.name),
        "total_instances": len(out_instances),
        "instances": out_instances,
    }


def write_csv(index: dict[str, Any], csv_path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for inst in index.get("instances", []):
        files = inst.get("files", {})
        problems = inst.get("problems", [])
        if isinstance(problems, list):
            problems_str = ";".join(str(p) for p in problems)
        else:
            problems_str = str(problems)

        rows.append(
            {
                "id": inst.get("id"),
                "difficulty": inst.get("difficulty"),
                "format": inst.get("format"),
                "num_claims": inst.get("num_claims"),
                "pages_estimate": inst.get("pages_estimate"),
                "pdf_pages": files.get("pdf_pages"),
                "problems": problems_str,
                "pdf_size_bytes": files.get("pdf_size_bytes"),
                "html_size_bytes": files.get("html_size_bytes"),
                "json_size_bytes": files.get("json_size_bytes"),
            }
        )

    fieldnames = [
        "id",
        "difficulty",
        "format",
        "num_claims",
        "pages_estimate",
        "pdf_pages",
        "problems",
        "pdf_size_bytes",
        "html_size_bytes",
        "json_size_bytes",
    ]

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_html(index: dict[str, Any], html_path: Path) -> None:
    instances = index.get("instances", [])

    difficulty_counts: dict[str, int] = {}
    format_counts: dict[str, int] = {}
    for inst in instances:
        d = str(inst.get("difficulty") or "")
        f = str(inst.get("format") or "")
        difficulty_counts[d] = difficulty_counts.get(d, 0) + 1
        format_counts[f] = format_counts.get(f, 0) + 1

    def _fmt_bytes(n: int | None) -> str:
        if n is None:
            return ""
        if n < 1024:
            return f"{n} B"
        if n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        return f"{n / (1024 * 1024):.2f} MB"

    rows_html: list[str] = []
    for inst in instances:
        inst_id = str(inst.get("id") or "")
        files = inst.get("files", {})
        problems = inst.get("problems", [])
        problems_str = ", ".join(str(p) for p in problems) if isinstance(problems, list) else str(problems)

        pdf_name = str(files.get("pdf") or "")
        html_name = str(files.get("html") or "")
        gt_name = str(files.get("ground_truth") or "")

        pdf_href = "./" + quote(pdf_name) if pdf_name else ""
        html_href = "./" + quote(html_name) if html_name else ""
        gt_href = "./" + quote(gt_name) if gt_name else ""

        pdf_pages = files.get("pdf_pages")
        pdf_pages_str = "" if pdf_pages is None else str(pdf_pages)

        rows_html.append(
            "\n".join(
                [
                    "<tr>",
                    f"  <td class=\"mono\">{escape(inst_id)}</td>",
                    f"  <td>{escape(str(inst.get('difficulty') or ''))}</td>",
                    f"  <td>{escape(str(inst.get('format') or ''))}</td>",
                    f"  <td class=\"num\">{escape(str(inst.get('num_claims') or ''))}</td>",
                    f"  <td class=\"num\">{escape(str(inst.get('pages_estimate') or ''))}</td>",
                    f"  <td class=\"num\">{escape(pdf_pages_str)}</td>",
                    f"  <td>{escape(problems_str)}</td>",
                    "  <td>",
                    f"    <a href=\"{escape(pdf_href)}\" target=\"_blank\" rel=\"noopener noreferrer\">pdf</a>",
                    f"    <a href=\"{escape(html_href)}\" target=\"_blank\" rel=\"noopener noreferrer\">html</a>",
                    f"    <a href=\"{escape(gt_href)}\" target=\"_blank\" rel=\"noopener noreferrer\">json</a>",
                    "  </td>",
                    f"  <td class=\"num\">{escape(_fmt_bytes(files.get('pdf_size_bytes')))}</td>",
                    f"  <td class=\"num\">{escape(_fmt_bytes(files.get('html_size_bytes')))}</td>",
                    f"  <td class=\"num\">{escape(_fmt_bytes(files.get('json_size_bytes')))}</td>",
                    "</tr>",
                ]
            )
        )

    built_at = escape(str(index.get("built_at") or ""))
    dataset_dir = escape(str(index.get("dataset_dir") or ""))
    total_instances = escape(str(index.get("total_instances") or ""))

    difficulty_summary = ", ".join(
        f"{escape(k)}: {v}" for k, v in sorted(difficulty_counts.items()) if k
    )
    format_summary = ", ".join(
        f"{escape(k)}: {v}" for k, v in sorted(format_counts.items()) if k
    )

    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Benchmark Instance Index</title>
  <style>
    :root {{
      --bg: #0b0e14;
      --panel: #121826;
      --text: #e6e6e6;
      --muted: #a0a0a0;
      --border: #2a3142;
      --header: #171f30;
      --link: #8ab4ff;
    }}

    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
      background: var(--bg);
      color: var(--text);
    }}

    .container {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
    }}

    h1 {{
      margin: 0 0 8px 0;
      font-size: 20px;
      font-weight: 650;
    }}

    .meta {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
      margin-bottom: 16px;
    }}

    .panel {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px;
      margin-bottom: 16px;
    }}

    .controls {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}

    input[type=\"search\"] {{
      flex: 1;
      min-width: 260px;
      background: #0f1420;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 12px;
      outline: none;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}

    thead th {{
      position: sticky;
      top: 0;
      background: var(--header);
      border-bottom: 1px solid var(--border);
      padding: 10px;
      text-align: left;
      white-space: nowrap;
      cursor: pointer;
      user-select: none;
    }}

    tbody td {{
      border-top: 1px solid var(--border);
      padding: 10px;
      vertical-align: top;
    }}

    tbody tr:hover {{
      background: rgba(255, 255, 255, 0.03);
    }}

    a {{
      color: var(--link);
      text-decoration: none;
      margin-right: 10px;
    }}

    a:hover {{
      text-decoration: underline;
    }}

    .mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }}

    .num {{
      text-align: right;
      white-space: nowrap;
    }}

    .hint {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 10px;
    }}
  </style>
</head>
<body>
  <div class=\"container\">
    <h1>Benchmark Instance Index</h1>
    <div class=\"meta\">
      <div><span class=\"mono\">{dataset_dir}</span></div>
      <div>Built at: <span class=\"mono\">{built_at}</span></div>
      <div>Total instances: <span class=\"mono\">{total_instances}</span></div>
      <div>By tier: <span class=\"mono\">{difficulty_summary}</span></div>
      <div>By format: <span class=\"mono\">{format_summary}</span></div>
    </div>

    <div class=\"panel\">
      <div class=\"controls\">
        <input id=\"search\" type=\"search\" placeholder=\"Filter by id / problems / tier / format...\" oninput=\"filterRows()\" />
      </div>
      <div class=\"hint\">Click a column header to sort. Links open the corresponding PDF/HTML/JSON in this directory.</div>
    </div>

    <div class=\"panel\" style=\"padding: 0; overflow-x: auto;\">
      <table id=\"index\">
        <thead>
          <tr>
            <th data-type=\"text\">id</th>
            <th data-type=\"text\">tier</th>
            <th data-type=\"text\">format</th>
            <th data-type=\"num\" class=\"num\">claims</th>
            <th data-type=\"num\" class=\"num\">est. pages</th>
            <th data-type=\"num\" class=\"num\">pdf pages</th>
            <th data-type=\"text\">problems</th>
            <th data-type=\"text\">files</th>
            <th data-type=\"num\" class=\"num\">pdf size</th>
            <th data-type=\"num\" class=\"num\">html size</th>
            <th data-type=\"num\" class=\"num\">json size</th>
          </tr>
        </thead>
        <tbody>
          {"\n".join(rows_html)}
        </tbody>
      </table>
    </div>
  </div>

  <script>
    function normalize(s) {{
      return (s || '').toString().toLowerCase();
    }}

    function filterRows() {{
      const q = normalize(document.getElementById('search').value);
      const tbody = document.querySelector('#index tbody');
      for (const tr of tbody.querySelectorAll('tr')) {{
        const text = normalize(tr.innerText);
        tr.style.display = text.includes(q) ? '' : 'none';
      }}
    }}

    let sortState = {{ idx: null, asc: true }};

    function getCellValue(tr, idx) {{
      const td = tr.children[idx];
      return td ? td.innerText.trim() : '';
    }}

    function toNumber(s) {{
      const n = Number((s || '').replace(/[^0-9.]/g, ''));
      return Number.isFinite(n) ? n : -1;
    }}

    function sortTable(idx, type) {{
      const tbody = document.querySelector('#index tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      const asc = (sortState.idx === idx) ? !sortState.asc : true;
      sortState = {{ idx, asc }};

      rows.sort((a, b) => {{
        const av = getCellValue(a, idx);
        const bv = getCellValue(b, idx);
        if (type === 'num') {{
          return asc ? (toNumber(av) - toNumber(bv)) : (toNumber(bv) - toNumber(av));
        }}
        return asc ? av.localeCompare(bv) : bv.localeCompare(av);
      }});

      for (const r of rows) {{
        tbody.appendChild(r);
      }}
    }}

    for (const th of document.querySelectorAll('#index thead th')) {{
      th.addEventListener('click', () => sortTable(th.cellIndex, th.dataset.type || 'text'));
    }}
  </script>
</body>
</html>
"""

    html_path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an instance index (CSV/JSON) for a generated benchmark dataset directory")
    parser.add_argument(
        "--input",
        type=str,
        default=str(Path(__file__).parent / "claims"),
        help="Dataset directory containing metadata.json (default: benchmarks/claims)",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="index.json",
        help="Output JSON filename (default: index.json)",
    )
    parser.add_argument(
        "--csv-out",
        type=str,
        default="index.csv",
        help="Output CSV filename (default: index.csv)",
    )
    parser.add_argument(
        "--html-out",
        type=str,
        default="index.html",
        help="Output HTML filename (default: index.html)",
    )

    args = parser.parse_args()

    dataset_dir = Path(args.input)
    if not dataset_dir.is_absolute():
        dataset_dir = (Path.cwd() / dataset_dir).resolve()

    metadata_path = dataset_dir / "metadata.json"
    if not metadata_path.exists():
        raise SystemExit(f"metadata.json not found in: {dataset_dir}")

    index = build_instance_index(dataset_dir=dataset_dir)

    json_path = dataset_dir / args.json_out
    csv_path = dataset_dir / args.csv_out
    html_path = dataset_dir / args.html_out

    json_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    write_csv(index=index, csv_path=csv_path)
    write_html(index=index, html_path=html_path)

    if pdfinfo_from_path is None:
        print("index built, but PDF page counts were not computed (missing dependency: pdf2image)")

    print(f"✓ Wrote: {json_path}")
    print(f"✓ Wrote: {csv_path}")
    print(f"✓ Wrote: {html_path}")


if __name__ == "__main__":
    main()
