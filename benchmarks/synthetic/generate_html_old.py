"""Generate HTML from structured claim data with intentional problems for benchmarking.

Problems injected:
1. Rows split across pages (page breaks)
2. Multi-row entities (cells with line breaks)
3. Exact duplicates
4. Large documents
5. Multiple tables (relevant + irrelevant content)
6. Multi-column layout (research paper style)
7. Merged cells
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from faker import Faker

fake = Faker()


class HTMLGenerator:
    """Generate HTML with various document complexity problems."""

    def __init__(self, seed: int | None = None):
        if seed is not None:
            random.seed(seed)
            Faker.seed(seed)

    @staticmethod
    def _html_header(title: str, use_columns: bool = False) -> str:
        """Generate HTML header with CSS."""
        column_css = """
            .multi-column {
                column-count: 2;
                column-gap: 40px;
                column-rule: 1px solid #ddd;
            }
        """ if use_columns else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        @page {{
            size: A4;
            margin: 2cm;
        }}
        body {{
            font-family: Arial, sans-serif;
            font-size: 10pt;
            line-height: 1.4;
        }}
        h1 {{
            font-size: 18pt;
            margin-bottom: 10px;
        }}
        h2 {{
            font-size: 14pt;
            margin-top: 20px;
            margin-bottom: 10px;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin-bottom: 20px;
            page-break-inside: auto;
        }}
        tr {{
            page-break-inside: avoid;
            page-break-after: auto;
        }}
        th, td {{
            border: 1px solid #333;
            padding: 6px;
            text-align: left;
            vertical-align: top;
        }}
        th {{
            background-color: #e0e0e0;
            font-weight: bold;
        }}
        .page-break {{
            page-break-before: always;
        }}
        .merged-cell {{
            background-color: #f9f9f9;
        }}
        .multi-line {{
            white-space: pre-line;
        }}
        {column_css}
    </style>
</head>
<body>
"""

    @staticmethod
    def _html_footer() -> str:
        return "\n</body>\n</html>"

    def _create_claim_table(
        self,
        claims: list[dict[str, Any]],
        force_page_breaks: bool = False,
        use_merged_cells: bool = False,
        multi_row_entities: bool = False,
    ) -> str:
        """Generate HTML table from claims with optional problems."""
        if not claims:
            return ""

        headers = list(claims[0].keys())
        html = '<table>\n<thead><tr>'

        for h in headers:
            html += f'<th>{h.replace("_", " ").title()}</th>'
        html += '</tr></thead>\n<tbody>\n'

        for i, claim in enumerate(claims):
            # Problem 1: Force page breaks mid-table
            if force_page_breaks and i > 0 and i % 15 == 0:
                html += '<tr class="page-break"><td colspan="100%"></td></tr>\n'

            # Problem 7: Merged cells (occasionally merge status + notes)
            if use_merged_cells and random.random() < 0.1 and "notes" in claim:
                html += "<tr>"
                for h in headers:
                    if h == "status":
                        merged_content = f"{claim['status']}\n---\n{claim.get('notes', '')}"
                        html += f'<td rowspan="1" colspan="2" class="merged-cell multi-line">{merged_content}</td>'
                    elif h == "notes":
                        continue  # Skip, already merged
                    else:
                        value = claim.get(h, "")
                        if value is None:
                            value = ""
                        
                        # Problem 2: Multi-row entities (split address, description)
                        if multi_row_entities and h in ["incident_location", "description"]:
                            value = str(value).replace(", ", "\n")
                        
                        html += f'<td class="multi-line">{value}</td>'
                html += "</tr>\n"
            else:
                html += "<tr>"
                for h in headers:
                    value = claim.get(h, "")
                    if value is None:
                        value = ""
                    
                    # Problem 2: Multi-row entities
                    if multi_row_entities and h in ["incident_location", "description"]:
                        value = str(value).replace(", ", "\n")
                    
                    html += f'<td class="multi-line">{value}</td>'
                html += "</tr>\n"

        html += "</tbody>\n</table>\n"
        return html

    def _create_irrelevant_table(self) -> str:
        """Problem 5: Generate irrelevant table (company directory, etc.)."""
        html = "<h2>Company Directory (Irrelevant)</h2>\n"
        html += "<table>\n<thead><tr><th>Employee</th><th>Department</th><th>Email</th></tr></thead>\n<tbody>\n"
        
        for _ in range(random.randint(5, 12)):
            html += f"<tr><td>{fake.name()}</td><td>{fake.job()}</td><td>{fake.email()}</td></tr>\n"
        
        html += "</tbody>\n</table>\n"
        return html

    def generate(
        self,
        claims: list[dict[str, Any]],
        problems: dict[str, bool] | None = None,
    ) -> str:
        """Generate HTML with specified problems enabled.
        
        Args:
            claims: List of claim dictionaries
            problems: Dict of problem flags:
                - page_breaks: Rows split across pages
                - multi_row: Multi-row entities
                - duplicates: Add exact duplicate claims
                - large_doc: Generate large document
                - multiple_tables: Add irrelevant tables
                - multi_column: Use multi-column layout
                - merged_cells: Use merged cells
        """
        if problems is None:
            problems = {}

        # Problem 3: Add exact duplicates
        if problems.get("duplicates", False):
            duplicate_indices = random.sample(range(len(claims)), k=min(5, len(claims) // 10))
            for idx in duplicate_indices:
                claims.insert(random.randint(0, len(claims)), claims[idx].copy())

        # Problem 4: Large documents (repeat claims if needed)
        if problems.get("large_doc", False) and len(claims) < 500:
            original_count = len(claims)
            while len(claims) < 500:
                claims.extend([c.copy() for c in claims[:original_count]])

        title = f"Insurance Claims Report ({len(claims)} records)"
        html = self._html_header(title, use_columns=problems.get("multi_column", False))

        # Problem 6: Multi-column layout wrapper
        if problems.get("multi_column", False):
            html += '<div class="multi-column">\n'

        html += f"<h1>{title}</h1>\n"
        html += f"<p>Generated on: {fake.date()}</p>\n"

        # Problem 5: Add irrelevant content
        if problems.get("multiple_tables", False):
            html += self._create_irrelevant_table()

        # Main claims table
        html += "<h2>Claims Data</h2>\n"
        html += self._create_claim_table(
            claims,
            force_page_breaks=problems.get("page_breaks", False),
            use_merged_cells=problems.get("merged_cells", False),
            multi_row_entities=problems.get("multi_row", False),
        )

        # Problem 5: Add another irrelevant table
        if problems.get("multiple_tables", False):
            html += self._create_irrelevant_table()

        if problems.get("multi_column", False):
            html += '</div>\n'

        html += self._html_footer()
        return html


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate HTML from claim JSON with intentional problems."
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Input JSON file with claims",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output HTML file",
    )
    parser.add_argument(
        "--page-breaks",
        action="store_true",
        help="Problem 1: Split rows across pages",
    )
    parser.add_argument(
        "--multi-row",
        action="store_true",
        help="Problem 2: Multi-row entities",
    )
    parser.add_argument(
        "--duplicates",
        action="store_true",
        help="Problem 3: Add exact duplicates",
    )
    parser.add_argument(
        "--large-doc",
        action="store_true",
        help="Problem 4: Generate large document (500+ claims)",
    )
    parser.add_argument(
        "--multiple-tables",
        action="store_true",
        help="Problem 5: Add irrelevant tables",
    )
    parser.add_argument(
        "--multi-column",
        action="store_true",
        help="Problem 6: Use multi-column layout",
    )
    parser.add_argument(
        "--merged-cells",
        action="store_true",
        help="Problem 7: Use merged cells",
    )
    parser.add_argument(
        "--all-problems",
        action="store_true",
        help="Enable all problems",
    )
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        default=42,
        help="Random seed",
    )

    args = parser.parse_args()

    # Read input JSON
    with open(args.input, encoding="utf-8") as f:
        claims = json.load(f)

    # Build problem configuration
    problems = {
        "page_breaks": args.all_problems or args.page_breaks,
        "multi_row": args.all_problems or args.multi_row,
        "duplicates": args.all_problems or args.duplicates,
        "large_doc": args.all_problems or args.large_doc,
        "multiple_tables": args.all_problems or args.multiple_tables,
        "multi_column": args.all_problems or args.multi_column,
        "merged_cells": args.all_problems or args.merged_cells,
    }

    # Generate HTML
    generator = HTMLGenerator(seed=args.seed)
    html = generator.generate(claims, problems=problems)

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    enabled = [k for k, v in problems.items() if v]
    print(f"✓ Generated HTML → {output_path}")
    print(f"  Problems enabled: {', '.join(enabled) if enabled else 'none'}")


if __name__ == "__main__":
    main()
