import json
import unittest
from unittest import mock

from benchmarks import evaluate_models, regime_agentic, regime_chunked, regime_oneshot


def _full_incident(num: str = "#30001") -> dict:
    """A schema-complete incident usable as a prediction fixture."""
    fb = {"reserve": 0.0, "paid": 0.0, "recovered": 0.0, "total_incurred": 0.0}
    return {
        "incident_number": num,
        "reference_number": "L230001",
        "company_name": "Acme Trucking",
        "division": "General",
        "coverage_type": "Liability",
        "status": "Open",
        "policy_number": "P1",
        "policy_state": "CA",
        "cause_code": None,
        "description": "rear-end collision",
        "handler": "Claims Adjuster",
        "unit_number": None,
        "date_of_loss": "01/01/2023",
        "loss_state": "CA",
        "date_reported": "01/02/2023",
        "agency": None,
        "insured": "Acme Trucking",
        "claimants": [],
        "driver_name": None,
        "bi": dict(fb),
        "pd": dict(fb),
        "lae": dict(fb),
        "ded": dict(fb),
        "adjuster_notes": None,
    }


class Gpt55RegimeRegistrationTests(unittest.TestCase):
    """All three GPT-5.5 regimes are registered and wired to the right extractors."""

    def test_three_gpt55_regimes_registered(self) -> None:
        expected = {
            "gpt55_oneshot": regime_oneshot.extract_with_openai_oneshot,
            "gpt55_chunked": regime_chunked.extract_with_openai,
            "gpt55_agent": regime_agentic.extract_with_openai_agent,
        }
        for key, extract_fn in expected.items():
            self.assertIn(key, evaluate_models.MODELS)
            cfg = evaluate_models.MODELS[key]
            self.assertIs(cfg.extract_fn, extract_fn)
            self.assertEqual(cfg.provider, "OpenAI")


class AgenticExtractionTests(unittest.TestCase):
    def test_extract_with_openai_agent_parses_session_file(self) -> None:
        payload = json.dumps({"incidents": [_full_incident()]}).encode("utf-8")
        # Seam returns a result dict; the session-file path wins over final_output.
        seam = {"final_output": None, "file_bytes": payload, "usage": None, "behavior": []}
        with mock.patch.object(regime_agentic, "_run_agent_extraction", return_value=seam):
            result = regime_agentic.extract_with_openai_agent(
                client=None, ocr_text="irrelevant ocr text", model_id="gpt-5.5"
            )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["incident_number"], "#30001")

    def test_extract_with_openai_agent_falls_back_to_final_output(self) -> None:
        fenced = "```json\n" + json.dumps({"incidents": [_full_incident("#30002")]}) + "\n```"
        # No file bytes -> recover from final_output via parse_json_response.
        seam = {"final_output": fenced, "file_bytes": None, "usage": None, "behavior": []}
        with mock.patch.object(regime_agentic, "_run_agent_extraction", return_value=seam):
            result = regime_agentic.extract_with_openai_agent(
                client=None, ocr_text="irrelevant", model_id="gpt-5.5"
            )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["incident_number"], "#30002")

    def test_extract_with_openai_agent_raises_when_no_output(self) -> None:
        seam = {"final_output": None, "file_bytes": None, "usage": None, "behavior": []}
        with mock.patch.object(regime_agentic, "_run_agent_extraction", return_value=seam):
            with self.assertRaises(ValueError):
                regime_agentic.extract_with_openai_agent(
                    client=None, ocr_text="irrelevant", model_id="gpt-5.5"
                )

    def test_extract_with_openai_agent_switches_to_policy_records(self) -> None:
        payload = json.dumps(
            {
                "records": [
                    {
                        "record_type": "policy_form_item",
                        "policy_number": "P-1",
                        "form_number": "CG 00 01",
                        "form_title": "Commercial General Liability Coverage Form",
                    }
                ]
            }
        ).encode("utf-8")
        ground_truth = [
            {
                "record_type": "policy_form_item",
                "policy_number": "P-1",
                "form_number": "CG 00 01",
                "form_title": "Commercial General Liability Coverage Form",
            }
        ]
        seam = {"final_output": None, "file_bytes": payload, "usage": None, "behavior": []}
        with mock.patch.object(regime_agentic, "_run_agent_extraction", return_value=seam) as run_agent:
            result = regime_agentic.extract_with_openai_agent(
                client=None,
                ocr_text="policy ocr text",
                model_id="gpt-5.5",
                ground_truth=ground_truth,
                sample="mixed_cgl_040_001",
            )
        self.assertEqual(result, ground_truth)
        args = run_agent.call_args.args
        self.assertIn("records.json", args[5])
        self.assertIn("policy_form_item", args[4])

    def test_agent_contract_includes_ifta_return_totals(self) -> None:
        ground_truth = [
            {
                "schedule": "Quarterly Return 0",
                "jurisdiction": "PA",
                "distance_miles": 1200,
                "total_due": 24.50,
            }
        ]

        instructions, _task, _output, expects_records = regime_agentic._build_agent_contract(
            ground_truth
        )

        self.assertTrue(expects_records)
        self.assertIn("IFTA return-schedule rules:", instructions)
        self.assertIn("every row labeled Return Totals", instructions)


class OpenAiOneshotTests(unittest.TestCase):
    def _fake_client(self, content: str) -> mock.MagicMock:
        # Mock the streaming structured-output API: client.beta.chat.completions.stream(...)
        # returns a context manager whose object is iterable and exposes
        # get_final_completion().
        message = mock.MagicMock()
        message.parsed = None  # force JSON parse of .content
        message.content = content
        final = mock.MagicMock()
        final.choices = [mock.MagicMock(message=message)]
        final.usage = None
        stream_obj = mock.MagicMock()
        stream_obj.__iter__ = lambda self: iter(())
        stream_obj.get_final_completion.return_value = final
        cm = mock.MagicMock()
        cm.__enter__.return_value = stream_obj
        cm.__exit__.return_value = False
        client = mock.MagicMock()
        client.beta.chat.completions.stream.return_value = cm
        return client

    def test_oneshot_single_call_with_large_budget(self) -> None:
        content = json.dumps({"incidents": [_full_incident("#40001")]})
        client = self._fake_client(content)
        result = regime_oneshot.extract_with_openai_oneshot(client, "ocr text", "gpt-5.5")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["incident_number"], "#40001")
        # One-shot makes exactly one (streamed) model call...
        client.beta.chat.completions.stream.assert_called_once()
        # ...with a large output budget (the model decides when to stop, not our cap).
        kwargs = client.beta.chat.completions.stream.call_args.kwargs
        self.assertGreaterEqual(kwargs["max_completion_tokens"], 32000)
        # ...and reasoning models get no temperature=0 (gpt-5.x rejects it).
        self.assertNotIn("temperature", kwargs)


if __name__ == "__main__":
    unittest.main()
