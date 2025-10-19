"""Generate realistic loss run HTML with complex multi-line item structure.

This version creates a more realistic loss run format with:
- Header information (carrier, account, policy details)
- Each incident as a detailed section
- Financial breakdown with separate line items per category (BI, PD, LAE, DED)
- Totals and subtotals
- Additional metadata and notes
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from faker import Faker

fake = Faker()


class LossRunHTMLGenerator:
    """Generate realistic loss run HTML documents.
    
    Supports two formats:
    - 'detailed': Detailed incident sections with line items (default)
    - 'table': Compact tabular format
    """

    def __init__(self, seed: int | None = None, format: str = "detailed"):
        if seed is not None:
            random.seed(seed)
            Faker.seed(seed)
        self.format = format

    @staticmethod
    def _generate_header_info(incidents: list[dict]) -> dict:
        """Generate header information for the loss run."""
        # Use first incident's company info
        company_name = incidents[0]["company_name"] if incidents else fake.company()
        account_num = f"A{random.randint(100000, 999999):07d}"
        
        return {
            "carrier_name": random.choice([
                "American Inter-Fidelity Exchange",
                "Sentry Insurance",
                "Continental Casualty",
                "National Interstate",
                "Great West Casualty"
            ]),
            "carrier_address": f"{random.randint(1000, 9999)} {fake.street_name()}, {fake.city()}, {fake.state_abbr()} {fake.zipcode()}",
            "carrier_phone": fake.phone_number(),
            "account_name": company_name,
            "account_number": account_num,
            "run_date": datetime.now().strftime("%m/%d/%Y"),
            "run_time": datetime.now().strftime("%I:%M %p"),
            "policy_period": "07/01/2023 - 07/01/2024",
            "policy_type": "Trucking"
        }

    def _html_header(self, title: str, use_columns: bool = False) -> str:
        """Generate HTML header with CSS for loss run format."""
        column_css = """
            .content-wrapper {{
                column-count: 2;
                column-gap: 40px;
                column-rule: 1px solid #ccc;
                column-fill: auto;
            }}
            .content-wrapper .incident-section {{
                break-inside: avoid;
                page-break-inside: avoid;
                -webkit-column-break-inside: avoid;
            }}
        """ if use_columns else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        @page {{
            size: A4 landscape;
            margin: 1.5cm;
        }}
        @media print {{
            .incident-section {{
                page-break-inside: avoid;
                break-inside: avoid-page;
            }}
            .page-break {{
                page-break-after: always;
                break-after: page;
            }}
        }}
        body {{
            font-family: 'Courier New', monospace;
            font-size: 8pt;
            line-height: 1.3;
            margin: 0;
            padding: 10px;
        }}
        .header {{
            margin-bottom: 15px;
            border-bottom: 2px solid #000;
            padding-bottom: 10px;
        }}
        .header-line {{
            margin: 2px 0;
        }}
        .company-name {{
            font-weight: bold;
            font-size: 11pt;
        }}
        .report-title {{
            text-align: right;
            font-weight: bold;
            font-size: 10pt;
        }}
        .incident-section {{
            margin-bottom: 20px;
            page-break-inside: avoid;
            break-inside: avoid;
            overflow: hidden;
        }}
        .incident-header {{
            background-color: #e8e8e8;
            padding: 5px;
            font-weight: bold;
            margin-bottom: 5px;
            border: 1px solid #000;
        }}
        .incident-details {{
            margin-left: 10px;
            margin-bottom: 8px;
        }}
        .detail-line {{
            margin: 2px 0;
        }}
        .label {{
            display: inline-block;
            width: 150px;
            font-weight: bold;
        }}
        .financial-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            font-size: 8pt;
        }}
        .financial-table th {{
            background-color: #d0d0d0;
            border: 1px solid #000;
            padding: 4px;
            text-align: right;
            font-weight: bold;
        }}
        .financial-table td {{
            border: 1px solid #666;
            padding: 4px;
            text-align: right;
        }}
        .financial-table td.category {{
            text-align: left;
            font-weight: bold;
        }}
        .total-row {{
            background-color: #f0f0f0;
            font-weight: bold;
        }}
        .grand-total-section {{
            margin-top: 30px;
            padding: 10px;
            background-color: #e8e8e8;
            border: 2px solid #000;
            font-weight: bold;
        }}
        .footer {{
            margin-top: 20px;
            padding-top: 10px;
            border-top: 1px solid #000;
            font-size: 7pt;
            text-align: center;
        }}
        .page-break {{
            page-break-before: always;
            break-before: page;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px dashed #ccc;
        }}
        .claimants-list {{
            margin-left: 20px;
            font-style: italic;
        }}
        {column_css}
    </style>
</head>
<body>
"""

    @staticmethod
    def _html_footer() -> str:
        return """
    <div class="footer">
        CONFIDENTIAL - NOT FOR AUDIT: MANAGERIAL USE ONLY
    </div>
</body>
</html>"""

    def _format_currency(self, amount: float) -> str:
        """Format amount as currency."""
        if amount == 0:
            return "$0.00"
        return f"${amount:,.2f}" if amount > 0 else f"(${abs(amount):,.2f})"

    def _generate_document_header(self, header_info: dict) -> str:
        """Generate the document header section."""
        return f"""
<div class="header">
    <div style="display: flex; justify-content: space-between;">
        <div>
            <div class="company-name">{header_info['carrier_name']}</div>
            <div class="header-line">{header_info['carrier_address']}</div>
            <div class="header-line">Phone: {header_info['carrier_phone']}</div>
        </div>
        <div class="report-title">
            Loss Run - Detailed Format
        </div>
    </div>
    <div style="margin-top: 10px;">
        <div class="header-line"><strong>Account:</strong> {header_info['account_name']}, Acct. # {header_info['account_number']}</div>
        <div class="header-line"><strong>Policy Period:</strong> {header_info['policy_period']} ({header_info['policy_type']})</div>
        <div class="header-line"><strong>Run Date/Time:</strong> {header_info['run_date']}, {header_info['run_time']}</div>
    </div>
</div>
"""

    def _generate_incident_section(self, incident: dict, incident_num: int, problems: dict) -> str:
        """Generate a detailed incident section with financial line items."""
        # Extract data
        inc_num = incident.get("incident_number", f"#{incident_num}")
        ref_num = incident.get("reference_number", "")
        coverage = incident.get("coverage_type", "Liability")
        status = incident.get("status", "Open")
        description = incident.get("description", "")
        loss_date = incident.get("date_of_loss", "")
        reported_date = incident.get("date_reported", "")
        loss_state = incident.get("loss_state", "")
        policy_num = incident.get("policy_number", "")
        policy_state = incident.get("policy_state", "")
        driver = incident.get("driver_name") or ""
        claimants = incident.get("claimants", [])
        unit = incident.get("unit_number") or ""
        agency = incident.get("agency") or ""
        notes = incident.get("adjuster_notes") or ""
        
        # Problem 2: Multi-row entities - split addresses and descriptions
        if problems.get("multi_row", False):
            description = description.replace(". ", ".\n")
        
        # Build incident header
        html = f"""
<div class="incident-section">
    <div class="incident-header">
        Incident {inc_num} (Ref #{ref_num})
        <span style="float: right;">{coverage} - {status}</span>
    </div>
    <div class="incident-details">
        <div class="detail-line"><span class="label">Policy #:</span>{policy_num} ({policy_state})</div>
        <div class="detail-line"><span class="label">Date of Loss:</span>{loss_date} ({loss_state})</div>
        <div class="detail-line"><span class="label">Date Reported:</span>{reported_date}</div>"""
        
        if driver:
            html += f"""
        <div class="detail-line"><span class="label">Driver:</span>{driver}</div>"""
        
        if unit:
            html += f"""
        <div class="detail-line"><span class="label">Unit #:</span>{unit}</div>"""
        
        if agency:
            html += f"""
        <div class="detail-line"><span class="label">Agency:</span>{agency}</div>"""
        
        html += f"""
        <div class="detail-line"><span class="label">Description:</span></div>
        <div style="margin-left: 20px; margin-top: 5px; white-space: pre-line;">{description}</div>"""
        
        if claimants:
            html += f"""
        <div class="detail-line" style="margin-top: 5px;"><span class="label">Claimant(s):</span></div>
        <div class="claimants-list">"""
            for claimant in claimants:
                html += f"{claimant}<br>"
            html += "</div>"
        
        if notes:
            html += f"""
        <div class="detail-line" style="margin-top: 5px;"><span class="label">Adjuster Notes:</span></div>
        <div style="margin-left: 20px; font-style: italic;">{notes}</div>"""
        
        html += """
    </div>
"""
        
        # Financial breakdown table with separate rows per category
        bi = incident.get("bi", {})
        pd = incident.get("pd", {})
        lae = incident.get("lae", {})
        ded = incident.get("ded", {})
        
        # Calculate totals
        total_reserve = bi.get("reserve", 0) + pd.get("reserve", 0) + lae.get("reserve", 0) + ded.get("reserve", 0)
        total_paid = bi.get("paid", 0) + pd.get("paid", 0) + lae.get("paid", 0) + ded.get("paid", 0)
        total_recovered = bi.get("recovered", 0) + pd.get("recovered", 0) + lae.get("recovered", 0) + ded.get("recovered", 0)
        total_incurred = bi.get("total_incurred", 0) + pd.get("total_incurred", 0) + lae.get("total_incurred", 0) + ded.get("total_incurred", 0)
        
        html += """
    <table class="financial-table">
        <thead>
            <tr>
                <th style="text-align: left;">Category</th>
                <th>Reserve</th>
                <th>Paid</th>
                <th>Recovered</th>
                <th>Total Incurred</th>
            </tr>
        </thead>
        <tbody>"""
        
        # Add rows for each category (only if non-zero)
        categories = [
            ("BI", bi),
            ("PD", pd),
            ("LAE", lae),
            ("DED", ded)
        ]
        
        for cat_name, cat_data in categories:
            if cat_data and cat_data.get("total_incurred", 0) != 0:
                html += f"""
            <tr>
                <td class="category">{cat_name}</td>
                <td>{self._format_currency(cat_data.get("reserve", 0))}</td>
                <td>{self._format_currency(cat_data.get("paid", 0))}</td>
                <td>{self._format_currency(cat_data.get("recovered", 0))}</td>
                <td>{self._format_currency(cat_data.get("total_incurred", 0))}</td>
            </tr>"""
        
        # Incident total row
        html += f"""
            <tr class="total-row">
                <td class="category">Incident Total</td>
                <td>{self._format_currency(total_reserve)}</td>
                <td>{self._format_currency(total_paid)}</td>
                <td>{self._format_currency(total_recovered)}</td>
                <td>{self._format_currency(total_incurred)}</td>
            </tr>
        </tbody>
    </table>
</div>
"""
        
        return html

    def _generate_table_row(self, incident: dict, row_num: int, problems: dict, use_merged: bool = False) -> str:
        """Generate a single table row for table format."""
        inc_num = incident.get("incident_number", f"#{row_num}")
        ref_num = incident.get("reference_number", "")
        company = incident.get("company_name", "")
        coverage = incident.get("coverage_type", "")
        status = incident.get("status", "")
        policy = incident.get("policy_number", "")
        loss_date = incident.get("date_of_loss", "")
        loss_state = incident.get("loss_state", "")
        driver = incident.get("driver_name") or "—"
        description = incident.get("description", "")
        
        # Problem 2: Multi-row entities
        if problems.get("multi_row", False):
            description = description.replace(". ", ".<br>")
        
        # Get financial totals
        bi = incident.get("bi", {})
        pd = incident.get("pd", {})
        lae = incident.get("lae", {})
        ded = incident.get("ded", {})
        
        total_reserve = bi.get("reserve", 0) + pd.get("reserve", 0) + lae.get("reserve", 0) + ded.get("reserve", 0)
        total_paid = bi.get("paid", 0) + pd.get("paid", 0) + lae.get("paid", 0) + ded.get("paid", 0)
        total_incurred = bi.get("total_incurred", 0) + pd.get("total_incurred", 0) + lae.get("total_incurred", 0) + ded.get("total_incurred", 0)
        
        # Problem 7: Merged cells - randomly merge some cells
        rowspan = ""
        if use_merged and random.random() < 0.15:  # 15% chance of merged cell
            rowspan = ' rowspan="2"'
        
        return f"""
        <tr>
            <td{rowspan}>{inc_num}</td>
            <td>{ref_num}</td>
            <td>{company}</td>
            <td{rowspan}>{coverage}</td>
            <td>{status}</td>
            <td>{policy}</td>
            <td>{loss_date}</td>
            <td>{loss_state}</td>
            <td>{driver}</td>
            <td style="max-width: 200px; white-space: pre-line;">{description}</td>
            <td style="text-align: right;">{self._format_currency(total_reserve)}</td>
            <td style="text-align: right;">{self._format_currency(total_paid)}</td>
            <td style="text-align: right;">{self._format_currency(total_incurred)}</td>
        </tr>"""
    
    def _generate_table_format(self, incidents: list[dict], header_info: dict, problems: dict) -> str:
        """Generate compact table format for loss run."""
        html = f"""
<div class="table-section">
    <table class="claims-table" style="width: 100%; border-collapse: collapse; font-size: 7pt;">
        <thead>
            <tr style="background-color: #333; color: white;">
                <th style="padding: 5px; border: 1px solid #000;">Incident #</th>
                <th style="padding: 5px; border: 1px solid #000;">Reference #</th>
                <th style="padding: 5px; border: 1px solid #000;">Company</th>
                <th style="padding: 5px; border: 1px solid #000;">Coverage</th>
                <th style="padding: 5px; border: 1px solid #000;">Status</th>
                <th style="padding: 5px; border: 1px solid #000;">Policy #</th>
                <th style="padding: 5px; border: 1px solid #000;">Loss Date</th>
                <th style="padding: 5px; border: 1px solid #000;">State</th>
                <th style="padding: 5px; border: 1px solid #000;">Driver</th>
                <th style="padding: 5px; border: 1px solid #000;">Description</th>
                <th style="padding: 5px; border: 1px solid #000;">Reserve</th>
                <th style="padding: 5px; border: 1px solid #000;">Paid</th>
                <th style="padding: 5px; border: 1px solid #000;">Incurred</th>
            </tr>
        </thead>
        <tbody>"""
        
        use_merged = problems.get("merged_cells", False)
        skip_next = False
        
        for idx, incident in enumerate(incidents):
            # Problem 1: Page breaks
            if problems.get("page_breaks", False) and idx > 0 and idx % 15 == 0:
                html += """
        </tbody>
    </table>
</div>
<div class="page-break"></div>
<div class="table-section">
    <table class="claims-table" style="width: 100%; border-collapse: collapse; font-size: 7pt;">
        <thead>
            <tr style="background-color: #333; color: white;">
                <th style="padding: 5px; border: 1px solid #000;">Incident #</th>
                <th style="padding: 5px; border: 1px solid #000;">Reference #</th>
                <th style="padding: 5px; border: 1px solid #000;">Company</th>
                <th style="padding: 5px; border: 1px solid #000;">Coverage</th>
                <th style="padding: 5px; border: 1px solid #000;">Status</th>
                <th style="padding: 5px; border: 1px solid #000;">Policy #</th>
                <th style="padding: 5px; border: 1px solid #000;">Loss Date</th>
                <th style="padding: 5px; border: 1px solid #000;">State</th>
                <th style="padding: 5px; border: 1px solid #000;">Driver</th>
                <th style="padding: 5px; border: 1px solid #000;">Description</th>
                <th style="padding: 5px; border: 1px solid #000;">Reserve</th>
                <th style="padding: 5px; border: 1px solid #000;">Paid</th>
                <th style="padding: 5px; border: 1px solid #000;">Incurred</th>
            </tr>
        </thead>
        <tbody>"""
            
            if skip_next:
                skip_next = False
                continue
            
            row_html = self._generate_table_row(incident, idx + 1, problems, use_merged)
            
            # Check if this row has merged cells
            if use_merged and 'rowspan="2"' in row_html and idx < len(incidents) - 1:
                skip_next = True
            
            html += row_html
        
        html += """
        </tbody>
    </table>
</div>"""
        
        return html

    def generate(self, incidents: list[dict], problems: dict[str, bool] | None = None) -> str:
        """Generate complete loss run HTML document."""
        if problems is None:
            problems = {}
        
        # Problem 3: Add exact duplicates
        if problems.get("duplicates", False):
            duplicate_indices = random.sample(range(len(incidents)), k=min(5, len(incidents) // 10))
            for idx in duplicate_indices:
                incidents.insert(random.randint(0, len(incidents)), incidents[idx].copy())
        
        # Problem 4: Large documents
        if problems.get("large_doc", False) and len(incidents) < 500:
            original_count = len(incidents)
            while len(incidents) < 500:
                incidents.extend([i.copy() for i in incidents[:original_count]])
        
        # Generate header info
        header_info = self._generate_header_info(incidents)
        
        # Start HTML
        title = f"{header_info['account_name']} - Loss Run"
        html = self._html_header(title, use_columns=problems.get("multi_column", False))
        
        # Problem 6: Multi-column layout
        if problems.get("multi_column", False):
            html += '<div class="content-wrapper">\n'
        
        # Document header
        html += self._generate_document_header(header_info)
        
        # Problem 5: Add irrelevant content
        if problems.get("multiple_tables", False):
            html += self._generate_irrelevant_section()
        
        # Generate content based on format
        if self.format == "table":
            html += self._generate_table_format(incidents, header_info, problems)
        else:
            # Generate each incident in detailed format
            for idx, incident in enumerate(incidents, 1):
                # Problem 1: Page breaks
                if problems.get("page_breaks", False) and idx > 1 and idx % 10 == 0:
                    html += '<div class="page-break"></div>\n'
                
                html += self._generate_incident_section(incident, idx, problems)
        
        # Problem 5: More irrelevant content
        if problems.get("multiple_tables", False):
            html += self._generate_irrelevant_section()
        
        # Grand totals
        html += self._generate_grand_totals(incidents)
        
        if problems.get("multi_column", False):
            html += '</div>\n'
        
        html += self._html_footer()
        
        return html

    def _generate_irrelevant_section(self) -> str:
        """Generate irrelevant content section."""
        return f"""
<div style="margin: 30px 0; padding: 15px; background-color: #f5f5f5; border: 1px solid #ccc;">
    <h3>Company Directory (Reference Only)</h3>
    <table class="financial-table">
        <thead>
            <tr>
                <th style="text-align: left;">Employee</th>
                <th style="text-align: left;">Department</th>
                <th style="text-align: left;">Email</th>
                <th style="text-align: left;">Phone</th>
            </tr>
        </thead>
        <tbody>
"""[1:] + "\n".join([
            f"            <tr><td>{fake.name()}</td><td>{fake.job()[:20]}</td><td>{fake.email()}</td><td>{fake.phone_number()}</td></tr>"
            for _ in range(random.randint(5, 10))
        ]) + """
        </tbody>
    </table>
</div>
"""

    def _generate_grand_totals(self, incidents: list[dict]) -> str:
        """Generate grand totals section."""
        total_reserve = sum(
            inc.get("bi", {}).get("reserve", 0) +
            inc.get("pd", {}).get("reserve", 0) +
            inc.get("lae", {}).get("reserve", 0) +
            inc.get("ded", {}).get("reserve", 0)
            for inc in incidents
        )
        total_paid = sum(
            inc.get("bi", {}).get("paid", 0) +
            inc.get("pd", {}).get("paid", 0) +
            inc.get("lae", {}).get("paid", 0) +
            inc.get("ded", {}).get("paid", 0)
            for inc in incidents
        )
        total_recovered = sum(
            inc.get("bi", {}).get("recovered", 0) +
            inc.get("pd", {}).get("recovered", 0) +
            inc.get("lae", {}).get("recovered", 0) +
            inc.get("ded", {}).get("recovered", 0)
            for inc in incidents
        )
        total_incurred = sum(
            inc.get("bi", {}).get("total_incurred", 0) +
            inc.get("pd", {}).get("total_incurred", 0) +
            inc.get("lae", {}).get("total_incurred", 0) +
            inc.get("ded", {}).get("total_incurred", 0)
            for inc in incidents
        )
        
        return f"""
<div class="grand-total-section">
    <div style="font-size: 11pt; margin-bottom: 10px;">REPORT TOTALS</div>
    <table class="financial-table" style="width: 60%;">
        <thead>
            <tr>
                <th style="text-align: left;"></th>
                <th>Reserve</th>
                <th>Paid</th>
                <th>Recovered</th>
                <th>Total Incurred</th>
            </tr>
        </thead>
        <tbody>
            <tr class="total-row">
                <td class="category">Grand Total</td>
                <td>{self._format_currency(total_reserve)}</td>
                <td>{self._format_currency(total_paid)}</td>
                <td>{self._format_currency(total_recovered)}</td>
                <td>{self._format_currency(total_incurred)}</td>
            </tr>
        </tbody>
    </table>
    <div style="margin-top: 10px;">TOTAL NUMBER OF INCIDENTS: {len(incidents)}</div>
</div>
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate realistic loss run HTML from incident JSON."
    )
    parser.add_argument("-i", "--input", required=True, help="Input JSON file with incidents")
    parser.add_argument("-o", "--output", required=True, help="Output HTML file")
    parser.add_argument("--page-breaks", action="store_true", help="Problem 1: Split rows across pages")
    parser.add_argument("--multi-row", action="store_true", help="Problem 2: Multi-row entities")
    parser.add_argument("--duplicates", action="store_true", help="Problem 3: Add exact duplicates")
    parser.add_argument("--large-doc", action="store_true", help="Problem 4: Generate large document (500+ incidents)")
    parser.add_argument("--multiple-tables", action="store_true", help="Problem 5: Add irrelevant tables")
    parser.add_argument("--multi-column", action="store_true", help="Problem 6: Use multi-column layout")
    parser.add_argument("--merged-cells", action="store_true", help="Problem 7: Use merged cells")
    parser.add_argument("--all-problems", action="store_true", help="Enable all problems")
    parser.add_argument("-s", "--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--format", choices=["detailed", "table"], default="detailed", 
                        help="Output format: 'detailed' (default) or 'table'")

    args = parser.parse_args()

    # Read input JSON
    with open(args.input, encoding="utf-8") as f:
        incidents = json.load(f)

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
    generator = LossRunHTMLGenerator(seed=args.seed, format=args.format)
    html = generator.generate(incidents, problems=problems)

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    enabled = [k for k, v in problems.items() if v]
    print(f"✓ Generated HTML → {output_path}")
    print(f"  Problems enabled: {', '.join(enabled) if enabled else 'none'}")


if __name__ == "__main__":
    main()
