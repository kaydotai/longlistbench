import tempfile
import unittest
from pathlib import Path

from benchmarks.canonical_transcripts import generate_canonical_markdown_from_html


class CanonicalTranscriptTests(unittest.TestCase):
    def test_detailed_html_preserves_pages_and_labels(self) -> None:
        html = """
        <html><body>
        <div class="header"><div class="header-line">Header</div></div>
        <div class="incident-section">
          <div class="incident-header">Incident #30001<span>Liability - Open</span></div>
          <div class="incident-details">
            <div class="detail-line"><span class="label">Policy #:</span>L23A1000 (CA)</div>
          </div>
          <table class="financial-table">
            <thead><tr><th>Category</th><th>Reserve</th></tr></thead>
            <tbody><tr><td class="category">PD</td><td>$10.00</td></tr></tbody>
          </table>
        </div>
        <div class="page-break"></div>
        <div class="footer">CONFIDENTIAL</div>
        </body></html>
        """

        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "sample.html"
            html_path.write_text(html, encoding="utf-8")
            out = generate_canonical_markdown_from_html(html_path)

        self.assertIn("# Page 1", out)
        self.assertIn("# Page 2", out)
        self.assertIn("Incident #30001", out)
        self.assertIn("Policy #: L23A1000 (CA)", out)
        self.assertIn("| Category | Reserve |", out)
        self.assertIn("CONFIDENTIAL", out)

    def test_table_html_preserves_table_rows(self) -> None:
        html = """
        <html><body>
        <div class="table-section">
          <table class="claims-table">
            <thead><tr><th>Incident #</th><th>Reference #</th></tr></thead>
            <tbody><tr><td>#30001</td><td>L230001</td></tr></tbody>
          </table>
        </div>
        </body></html>
        """

        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "sample.html"
            html_path.write_text(html, encoding="utf-8")
            out = generate_canonical_markdown_from_html(html_path)

        self.assertIn("| Incident # | Reference # |", out)
        self.assertIn("| #30001 | L230001 |", out)


if __name__ == "__main__":
    unittest.main()
