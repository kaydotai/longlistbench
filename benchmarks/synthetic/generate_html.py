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
from datetime import datetime, timedelta
from pathlib import Path

from faker import Faker
from generate_claim_data import generate_incidents

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
        self.seed = seed
        self.format = format

    @staticmethod
    def _page_break_split_indices(total: int) -> set[int]:
        if total <= 0:
            return set()

        if total <= 12:
            return {max(2, total // 2)}

        if total <= 60:
            return {max(2, total // 2)}

        target_splits = min(15, max(3, total // 50))
        indices: set[int] = set()
        for i in range(1, target_splits + 1):
            idx = max(2, (total * i) // (target_splits + 1))
            if idx < total:
                indices.add(idx)

        return indices

    @staticmethod
    def _inject_multiline(text: str, line_break: str) -> str:
        if not text:
            return text

        if "\n" in text or "<br" in text:
            return text

        if ". " in text:
            out = text.replace(". ", f".{line_break}")
            if out != text:
                return out

        words = text.split()
        if len(words) >= 6:
            mid = len(words) // 2
            return " ".join(words[:mid]) + line_break + " ".join(words[mid:])
        if len(words) >= 2:
            return words[0] + line_break + " ".join(words[1:])
        return text + line_break

    def apply_document_problems(self, incidents: list[dict], problems: dict[str, bool]) -> list[dict]:
        incidents_out = [i.copy() for i in incidents]

        if problems.get("duplicates", False) and incidents_out:
            k = min(5, len(incidents_out) // 10)
            if k > 0:
                duplicate_indices = random.sample(range(len(incidents_out)), k=k)
                for idx in duplicate_indices:
                    incidents_out.insert(random.randint(0, len(incidents_out)), incidents_out[idx].copy())

        if problems.get("large_doc", False) and len(incidents_out) < 500:
            target_count = 500
            additional_needed = target_count - len(incidents_out)
            if additional_needed > 0:
                random_state = random.getstate()
                faker_state = fake.random.getstate()
                try:
                    extra_seed = None if self.seed is None else (self.seed + 9991)
                    extra_incidents = generate_incidents(additional_needed, seed=extra_seed, start_year=2023)
                    extra_dicts = [i.model_dump() for i in extra_incidents]
                finally:
                    random.setstate(random_state)
                    fake.random.setstate(faker_state)

                existing_seqs: list[int] = []
                for inc in incidents_out:
                    inc_num = str(inc.get("incident_number", ""))
                    if inc_num.startswith("#"):
                        try:
                            existing_seqs.append(int(inc_num[1:]) - 30000)
                        except ValueError:
                            pass
                next_seq = max(existing_seqs, default=len(incidents_out)) + 1

                for j, inc in enumerate(extra_dicts):
                    seq = next_seq + j
                    inc["incident_number"] = f"#{30000 + seq}"
                    loss_date = str(inc.get("date_of_loss", "01/01/2023"))
                    try:
                        ref_year = int(loss_date.split("/")[-1]) % 100
                    except ValueError:
                        ref_year = 23
                    inc["reference_number"] = f"L{ref_year}{seq:04d}"

                incidents_out.extend(extra_dicts)

        return incidents_out

    @staticmethod
    def _generate_header_info(incidents: list[dict]) -> dict:
        """Generate header information for the loss run."""
        # Use first incident's company info
        company_name = incidents[0]["company_name"] if incidents else fake.company()
        account_num = f"A{random.randint(100000, 999999):07d}"

        run_dt = datetime(2024, 1, 1) + timedelta(minutes=random.randint(0, 365 * 24 * 60 - 1))
        
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
            "run_date": run_dt.strftime("%m/%d/%Y"),
            "run_time": run_dt.strftime("%I:%M %p"),
            "policy_period": "07/01/2023 - 07/01/2024",
            "policy_type": "Trucking"
        }

    def _html_header(self, title: str, use_columns: bool = False) -> str:
        """Generate HTML header with CSS for loss run format."""
        column_css = """
            .content-wrapper {
                column-count: 2;
                column-gap: 40px;
                column-rule: 1px solid #ccc;
                column-fill: auto;
            }
            .content-wrapper .incident-section {
                break-inside: avoid;
                page-break-inside: avoid;
                -webkit-column-break-inside: avoid;
            }
            .content-wrapper .incident-section.split-incident {
                break-inside: auto;
                page-break-inside: auto;
                -webkit-column-break-inside: auto;
            }
            .content-wrapper .table-section {
                column-span: all;
                -webkit-column-span: all;
            }
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
            .incident-section.split-incident {{
                page-break-inside: auto;
                break-inside: auto;
            }}
            .page-break {{
                display: block !important;
                width: 100% !important;
                height: 1px !important;
                page-break-before: always !important;
                break-before: page !important;
            }}
        }}
        body {{
            font-family: 'Courier New', monospace;
            font-size: 8pt;
            line-height: 1.3;
            margin: 0;
            padding: 10px;
            background-color: #fff;
            color: #000;
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
        .incident-section.split-incident {{
            page-break-inside: auto;
            break-inside: auto;
            overflow: visible;
        }}
        .incident-section.split-incident > .incident-header {{
            background-color: #fff3cd;
        }}
        .content-wrapper .incident-section.split-incident {{
            overflow: hidden;
            column-span: none;
            -webkit-column-span: none;
        }}
        .content-wrapper .incident-section.split-incident > .incident-header {{
            column-span: none;
            -webkit-column-span: none;
        }}
        .content-wrapper .incident-section.split-incident .financial-table {{
            table-layout: fixed;
            width: 100%;
            max-width: 100%;
            font-size: 7pt;
        }}
        .content-wrapper .incident-section.split-incident .financial-table th,
        .content-wrapper .incident-section.split-incident .financial-table td {{
            padding: 2px;
        }}
        .continued-note {{
            margin: 6px 0;
            font-size: 7pt;
            text-align: center;
            font-style: italic;
            color: #444;
        }}
        .continued-header {{
            background-color: #fff3cd;
            padding: 5px;
            font-weight: bold;
            margin-bottom: 5px;
            border: 1px dashed #444;
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
            display: block;
            width: 100%;
            height: 1px;
            page-break-before: always;
            break-before: page;
            margin: 0;
            padding: 0;
            border: 0;
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

    def _generate_incident_section(
        self,
        incident: dict,
        incident_num: int,
        problems: dict,
        split_across_pages: bool = False,
        use_columns: bool = False,
    ) -> str:
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
        company_name = incident.get("company_name") or ""
        insured_name = incident.get("insured") or company_name
        driver = incident.get("driver_name") or ""
        claimants = incident.get("claimants", [])
        unit = incident.get("unit_number") or ""
        agency = incident.get("agency") or ""
        notes = incident.get("adjuster_notes") or ""
        
        # Problem 2: Multi-row entities - split addresses and descriptions
        if problems.get("multi_row", False):
            description = self._inject_multiline(description, "\n")
        
        # Build incident header
        incident_classes = "incident-section"
        if split_across_pages:
            incident_classes += " split-incident"

        html = f"""
<div class="{incident_classes}">
    <div class="incident-header">
        Incident {inc_num} (Ref #{ref_num})
        <span style="float: right;">{coverage} - {status}</span>
    </div>
    <div class="incident-details">
        <div class="detail-line"><span class="label">Policy #:</span>{policy_num} ({policy_state})</div>
        <div class="detail-line"><span class="label">Date of Loss:</span>{loss_date} ({loss_state})</div>
        <div class="detail-line"><span class="label">Date Reported:</span>{reported_date}</div>"""

        if company_name:
            html += f"""
        <div class="detail-line"><span class="label">Company:</span>{company_name}</div>"""

        if insured_name:
            html += f"""
        <div class="detail-line"><span class="label">Insured:</span>{insured_name}</div>"""

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

        if split_across_pages:
            html += '</div>\n'
            if use_columns:
                html += '</div>\n'
            html += '<div class="page-break"></div>\n'
            if use_columns:
                html += '<div class="content-wrapper">\n'
            html += '<div class="incident-section split-incident">\n'
            html += f'''    <div class="incident-header">
        Incident {inc_num} (Ref #{ref_num})
        <span style="float: right;">{coverage} - {status}</span>
    </div>\n'''

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

        if problems.get("merged_cells", False):
            thead = """
        <thead>
            <tr>
                <th style="text-align: left;" rowspan="2">Category</th>
                <th colspan="4">Financials</th>
            </tr>
            <tr>
                <th>Reserve</th>
                <th>Paid</th>
                <th>Recovered</th>
                <th>Total Incurred</th>
            </tr>
        </thead>"""
        else:
            thead = """
        <thead>
            <tr>
                <th style="text-align: left;">Category</th>
                <th>Reserve</th>
                <th>Paid</th>
                <th>Recovered</th>
                <th>Total Incurred</th>
            </tr>
        </thead>"""

        html += f"""
    <table class=\"financial-table\">
{thead}
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

    def _generate_table_row(
        self,
        incident: dict,
        row_num: int,
        problems: dict,
        use_merged: bool = False,
        rowspan: str = "",
        omit_merged_cells: bool = False,
        split_across_pages: bool = False,
    ) -> str:
        """Generate a single table row for table format."""
        inc_num = incident.get("incident_number", f"#{row_num}")
        ref_num = incident.get("reference_number", "")
        company = incident.get("company_name", "")
        insured = incident.get("insured") or company
        division = incident.get("division", "")
        handler = incident.get("handler", "")
        agency = incident.get("agency", "")
        coverage = incident.get("coverage_type", "")
        status = incident.get("status", "")
        policy = incident.get("policy_number", "")
        policy_state = incident.get("policy_state", "")
        loss_date = incident.get("date_of_loss", "")
        reported_date = incident.get("date_reported", "")
        loss_state = incident.get("loss_state", "")
        unit_number = incident.get("unit_number") or "—"
        driver = incident.get("driver_name") or "—"
        claimants = incident.get("claimants", [])
        claimants_text = ", ".join(claimants) if claimants else "—"
        cause_code = incident.get("cause_code", "")
        notes = incident.get("adjuster_notes", "")
        description = incident.get("description", "")
        
        # Problem 2: Multi-row entities
        if problems.get("multi_row", False):
            description = self._inject_multiline(description, "<br>")

        # Get financial totals
        bi = incident.get("bi", {})
        pd = incident.get("pd", {})
        lae = incident.get("lae", {})
        ded = incident.get("ded", {})
        
        total_reserve = bi.get("reserve", 0) + pd.get("reserve", 0) + lae.get("reserve", 0) + ded.get("reserve", 0)
        total_paid = bi.get("paid", 0) + pd.get("paid", 0) + lae.get("paid", 0) + ded.get("paid", 0)
        total_recovered = bi.get("recovered", 0) + pd.get("recovered", 0) + lae.get("recovered", 0) + ded.get("recovered", 0)
        total_incurred = bi.get("total_incurred", 0) + pd.get("total_incurred", 0) + lae.get("total_incurred", 0) + ded.get("total_incurred", 0)

        def _category_line(name: str, values: dict) -> str:
            return (
                f"{name}: Reserve {self._format_currency(values.get('reserve', 0))} | "
                f"Paid {self._format_currency(values.get('paid', 0))} | "
                f"Recovered {self._format_currency(values.get('recovered', 0))} | "
                f"Total Incurred {self._format_currency(values.get('total_incurred', 0))}"
            )

        details_lines = [
            f"Insured: {insured}",
            f"Division: {division}",
            f"Handler: {handler}",
            f"Agency: {agency}",
            f"Policy State: {policy_state}",
            f"Date Reported: {reported_date}",
            f"Unit Number: {unit_number}",
            f"Driver: {driver}",
            f"Claimants: {claimants_text}",
            f"Cause Code: {cause_code}",
            f"Description: {description}",
            f"Adjuster Notes: {notes}",
            _category_line("BI", bi),
            _category_line("PD", pd),
            _category_line("LAE", lae),
            _category_line("DED", ded),
            (
                f"Incident Total: Reserve {self._format_currency(total_reserve)} | "
                f"Paid {self._format_currency(total_paid)} | "
                f"Recovered {self._format_currency(total_recovered)} | "
                f"Total Incurred {self._format_currency(total_incurred)}"
            ),
        ]
        details_html = "<br>".join(details_lines)
        
        # Never omit incident_cell - it's a primary identifier that must always be present
        incident_cell = f"<td>{inc_num}</td>"
        coverage_cell = f"<td{rowspan}>{coverage}</td>" if not omit_merged_cells else ""
        
        return f"""
        <tr>
            {incident_cell}
            <td>{ref_num}</td>
            <td>{company}</td>
            {coverage_cell}
            <td>{status}</td>
            <td>{policy}</td>
            <td>{loss_date}</td>
            <td>{loss_state}</td>
            <td style="max-width: 520px; white-space: pre-line; line-height: 1.25;">{details_html}</td>
        </tr>"""
    
    def _generate_table_format(self, incidents: list[dict], header_info: dict, problems: dict) -> str:
        """Generate compact table format for loss run."""
        html = f"""
<div class="table-section">
    <table class="claims-table" style="width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 6pt;">
        <thead>
            <tr style="background-color: #333; color: white;">
                <th style="padding: 3px; border: 1px solid #000;">Incident #</th>
                <th style="padding: 3px; border: 1px solid #000;">Reference #</th>
                <th style="padding: 3px; border: 1px solid #000;">Company</th>
                <th style="padding: 3px; border: 1px solid #000;">Coverage</th>
                <th style="padding: 3px; border: 1px solid #000;">Status</th>
                <th style="padding: 3px; border: 1px solid #000;">Policy #</th>
                <th style="padding: 3px; border: 1px solid #000;">Loss Date</th>
                <th style="padding: 3px; border: 1px solid #000;">Loss State</th>
                <th style="padding: 3px; border: 1px solid #000;">Incident Details</th>
            </tr>
        </thead>
        <tbody>"""
        
        use_page_breaks = problems.get("page_breaks", False)
        split_rows = self._page_break_split_indices(len(incidents)) if use_page_breaks else set()
        use_merged = problems.get("merged_cells", False)
        omit_merged_cells = False
        merged_cells_inserted = False
        
        table_header = """        <thead>
            <tr style="background-color: #333; color: white;">
                <th style="padding: 3px; border: 1px solid #000;">Incident #</th>
                <th style="padding: 3px; border: 1px solid #000;">Reference #</th>
                <th style="padding: 3px; border: 1px solid #000;">Company</th>
                <th style="padding: 3px; border: 1px solid #000;">Coverage</th>
                <th style="padding: 3px; border: 1px solid #000;">Status</th>
                <th style="padding: 3px; border: 1px solid #000;">Policy #</th>
                <th style="padding: 3px; border: 1px solid #000;">Loss Date</th>
                <th style="padding: 3px; border: 1px solid #000;">Loss State</th>
                <th style="padding: 3px; border: 1px solid #000;">Incident Details</th>
            </tr>
        </thead>
        <tbody>"""

        for idx, incident in enumerate(incidents):
            row_num = idx + 1
            split_row = bool(use_page_breaks and (row_num in split_rows))
            
            if split_row:
                html += """
        </tbody>
    </table>
</div>
<div class="page-break"></div>
<div class="table-section">
    <table class="claims-table" style="width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 6pt;">
""" + table_header
            
            force_merge = use_merged and (not merged_cells_inserted) and (not omit_merged_cells) and idx < len(incidents) - 1
            start_merge = force_merge or (
                use_merged
                and (not omit_merged_cells)
                and idx < len(incidents) - 1
                and random.random() < 0.15
            )
            rowspan = ' rowspan="2"' if start_merge else ""

            html += self._generate_table_row(
                incident,
                row_num,
                problems,
                use_merged=use_merged,
                rowspan=rowspan,
                omit_merged_cells=omit_merged_cells,
                split_across_pages=False,  # Handled above now
            )

            omit_merged_cells = start_merge
            if start_merge:
                merged_cells_inserted = True
        
        html += """
        </tbody>
    </table>
</div>"""
        
        return html

    def generate(self, incidents: list[dict], problems: dict[str, bool] | None = None) -> str:
        """Generate complete loss run HTML document."""
        if problems is None:
            problems = {}
        
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
            use_page_breaks = problems.get("page_breaks", False)
            split_incidents = self._page_break_split_indices(len(incidents)) if use_page_breaks else set()
            for idx, incident in enumerate(incidents, 1):
                split_incident = bool(use_page_breaks and (idx in split_incidents))
                html += self._generate_incident_section(
                    incident,
                    idx,
                    problems,
                    split_across_pages=split_incident,
                    use_columns=problems.get("multi_column", False),
                )
        
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
    incidents = generator.apply_document_problems(incidents, problems)
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
