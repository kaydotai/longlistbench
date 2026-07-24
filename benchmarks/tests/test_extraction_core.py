import json
import unittest

from benchmarks.extraction_core import (
    build_record_extraction_prompt,
    parse_json_response,
)


class ExtractionCoreTests(unittest.TestCase):
    def test_build_record_extraction_prompt_uses_generic_records_contract(self):
        ground_truth = [
            {
                "record_type": "vehicle_state_mileage_row",
                "record_id": "hidden-001",
                "unit_number": "TRK-101",
                "jurisdiction": "PA",
                "taxable_miles": 1200,
            }
        ]

        prompt = build_record_extraction_prompt("OCR BODY", ground_truth)

        self.assertIn('{ "records": [ ... ] }', prompt)
        self.assertIn("vehicle_state_mileage_row", prompt)
        self.assertIn("unit_number", prompt)
        self.assertIn("jurisdiction", prompt)
        self.assertIn("taxable_miles", prompt)
        self.assertNotIn("hidden-001", prompt)
        self.assertNotIn("record_id", prompt)
        self.assertIn("OCR BODY", prompt)

    def test_parse_json_response_salvages_truncated_records_array(self):
        raw = json.dumps(
            {
                "records": [
                    {"unit_number": "TRK-101", "jurisdiction": "PA"},
                    {"unit_number": "TRK-102", "jurisdiction": "OH"},
                ]
            }
        )
        truncated = raw.rsplit("}", 1)[0]

        parsed = parse_json_response(truncated)

        self.assertEqual(
            parsed,
            {
                "records": [
                    {"unit_number": "TRK-101", "jurisdiction": "PA"},
                    {"unit_number": "TRK-102", "jurisdiction": "OH"},
                ]
            },
        )

    def test_policy_contract_defines_logical_record_scope(self):
        ground_truth = [
            {
                "record_type": "policy_clause_item",
                "clause_title": "Aggregate Limit Application",
                "clause_type": "condition",
                "clause_text": "The scheduled limit applies.",
            },
            {
                "record_type": "policy_premium_item",
                "location_number": "1",
                "premium": "$100",
            },
        ]

        prompt = build_record_extraction_prompt("OCR BODY", ground_truth)

        self.assertIn("Policy logical-record rules:", prompt)
        self.assertIn("one record per distinct logical policy item", prompt)
        self.assertIn("only the operative provision paragraph", prompt)
        self.assertIn("Exclude document-level totals", prompt)

    def test_ifta_return_schedule_contract_includes_return_totals_without_count(self):
        ground_truth = [
            {
                "schedule": "Quarterly Return 0",
                "jurisdiction": "PA",
                "surcharge": "N",
                "distance_miles": 1200,
                "total_due": 24.50,
            },
            {
                "schedule": "Return Totals (Quarterly Return 0)",
                "jurisdiction": "",
                "surcharge": "",
                "distance_miles": 1200,
                "total_due": 24.50,
            },
        ]

        prompt = build_record_extraction_prompt("OCR BODY", ground_truth)

        self.assertIn("IFTA return-schedule rules:", prompt)
        self.assertIn(
            "Include every jurisdiction row, every Non-IFTA row, and every row labeled Return Totals.",
            prompt,
        )
        self.assertIn("Exclude intermediate subtotals, payment lines, and remittance lines.", prompt)
        self.assertEqual(
            prompt,
            build_record_extraction_prompt("OCR BODY", ground_truth + [ground_truth[0]]),
        )

    def test_non_ifta_contract_does_not_include_return_schedule_rules(self):
        ground_truth = [
            {
                "record_type": "driver_record",
                "driver_name": "Jordan Lee",
                "jurisdiction": "PA",
            }
        ]

        prompt = build_record_extraction_prompt("OCR BODY", ground_truth)

        self.assertNotIn("IFTA return-schedule rules:", prompt)


if __name__ == "__main__":
    unittest.main()
