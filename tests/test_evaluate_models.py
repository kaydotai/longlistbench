import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from benchmarks import check_evaluation_report, evaluate_models
from benchmarks.evaluate_models import (
    EvaluationResult,
    _validate_and_normalize_predictions,
    generate_report,
    run_evaluation_from_saved_predictions,
)


class EvaluatorRegressionTests(unittest.TestCase):
    def test_checker_reuses_main_evaluator_metrics_function(self) -> None:
        self.assertIs(
            check_evaluation_report.evaluate_extraction,
            evaluate_models.evaluate_extraction,
        )

    def test_validator_rejects_missing_required_fields(self) -> None:
        with self.assertRaises(ValueError):
            _validate_and_normalize_predictions(
                [
                    {
                        "incident_number": "#30001",
                        "reference_number": "L230001",
                        "company_name": "X",
                        "coverage_type": "Liability",
                        "status": "Open",
                        "policy_number": "P1",
                        "policy_state": "CA",
                        "description": "desc",
                        "date_of_loss": "01/01/2023",
                        "loss_state": "CA",
                        "date_reported": "01/02/2023",
                        "insured": "X",
                        "claimants": [],
                    }
                ]
            )

    def test_report_weighted_scores_include_failed_samples(self) -> None:
        out_dir = Path(tempfile.mkdtemp())
        generate_report(
            [
                EvaluationResult(
                    model="gemini",
                    sample="ok",
                    tier="easy",
                    format="detailed",
                    transcript="canonical",
                    metrics={
                        "f1": 1.0,
                        "recall": 1.0,
                        "precision": 1.0,
                        "found": 10,
                        "ground_truth_count": 1,
                        "predicted_count": 1,
                        "missing": 0,
                        "extra": 0,
                        "total_gold_field_pairs": 10,
                        "total_pred_field_pairs": 10,
                    },
                    extraction_time=1.0,
                    error=None,
                ),
                EvaluationResult(
                    model="gemini",
                    sample="err",
                    tier="easy",
                    format="detailed",
                    transcript="canonical",
                    metrics={
                        "f1": 0.0,
                        "recall": 0.0,
                        "precision": 0.0,
                        "found": 0,
                        "ground_truth_count": 1,
                        "predicted_count": 0,
                        "missing": 1,
                        "extra": 0,
                        "total_gold_field_pairs": 10,
                        "total_pred_field_pairs": 0,
                    },
                    extraction_time=1.0,
                    error="boom",
                ),
            ],
            out_dir,
        )
        report = json.loads((out_dir / "evaluation_report.json").read_text(encoding="utf-8"))
        self.assertLess(report["model_stats"]["gemini"]["weighted_f1"], 1.0)

    def test_report_includes_transcript_condition_breakdown(self) -> None:
        out_dir = Path(tempfile.mkdtemp())
        generate_report(
            [
                EvaluationResult(
                    model="gemini",
                    sample="a",
                    tier="easy",
                    format="detailed",
                    transcript="canonical",
                    metrics={
                        "f1": 1.0,
                        "recall": 1.0,
                        "precision": 1.0,
                        "found": 10,
                        "ground_truth_count": 1,
                        "predicted_count": 1,
                        "missing": 0,
                        "extra": 0,
                        "total_gold_field_pairs": 10,
                        "total_pred_field_pairs": 10,
                    },
                    extraction_time=1.0,
                    error=None,
                ),
                EvaluationResult(
                    model="gemini",
                    sample="a",
                    tier="easy",
                    format="detailed",
                    transcript="ocr",
                    metrics={
                        "f1": 0.5,
                        "recall": 0.5,
                        "precision": 0.5,
                        "found": 5,
                        "ground_truth_count": 1,
                        "predicted_count": 1,
                        "missing": 0,
                        "extra": 0,
                        "total_gold_field_pairs": 10,
                        "total_pred_field_pairs": 10,
                    },
                    extraction_time=1.0,
                    error=None,
                ),
            ],
            out_dir,
        )
        report = json.loads((out_dir / "evaluation_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["detailed_results"][0]["transcript"], "canonical")
        self.assertIn("by_transcript", report["model_stats"]["gemini"])
        self.assertAlmostEqual(
            report["model_stats"]["gemini"]["by_transcript"]["canonical"]["weighted_f1"],
            1.0,
        )
        self.assertAlmostEqual(
            report["model_stats"]["gemini"]["by_transcript"]["ocr"]["weighted_f1"],
            0.5,
        )

    def test_report_marks_missing_slices_as_na(self) -> None:
        out_dir = Path(tempfile.mkdtemp())
        generate_report(
            [
                EvaluationResult(
                    model="gemini",
                    sample="easy_only",
                    tier="easy",
                    format="detailed",
                    transcript="canonical",
                    metrics={
                        "f1": 1.0,
                        "recall": 1.0,
                        "precision": 1.0,
                        "found": 10,
                        "ground_truth_count": 1,
                        "predicted_count": 1,
                        "missing": 0,
                        "extra": 0,
                        "total_gold_field_pairs": 10,
                        "total_pred_field_pairs": 10,
                    },
                    extraction_time=1.0,
                    error=None,
                ),
            ],
            out_dir,
        )

        markdown = (out_dir / "evaluation_report.md").read_text(encoding="utf-8")
        self.assertIn("| Gemini 2.5 | 100.0% | N/A | N/A | N/A |", markdown)
        self.assertIn("| Gemini 2.5 | 100.0% | N/A |", markdown)
        self.assertIn("| Gemini 2.5 | 100.0% | N/A |", markdown)

    def test_offline_evaluation_loads_transcript_specific_predictions(self) -> None:
        claims_dir = Path(tempfile.mkdtemp())
        results_dir = Path(tempfile.mkdtemp())

        sample = "easy_10_001_detailed"
        ground_truth = [
            {
                "incident_number": "#30001",
                "reference_number": "L230001",
                "company_name": "X",
                "division": "General",
                "coverage_type": "Liability",
                "status": "Open",
                "policy_number": "P1",
                "policy_state": "CA",
                "cause_code": None,
                "description": "desc",
                "handler": "Claims Adjuster",
                "unit_number": None,
                "date_of_loss": "01/01/2023",
                "loss_state": "CA",
                "date_reported": "01/02/2023",
                "agency": None,
                "insured": "X",
                "claimants": [],
                "driver_name": None,
                "bi": {"reserve": 0.0, "paid": 0.0, "recovered": 0.0, "total_incurred": 0.0},
                "pd": {"reserve": 10.0, "paid": 0.0, "recovered": 0.0, "total_incurred": 10.0},
                "lae": {"reserve": 0.0, "paid": 0.0, "recovered": 0.0, "total_incurred": 0.0},
                "ded": {"reserve": 0.0, "paid": 0.0, "recovered": 0.0, "total_incurred": 0.0},
                "adjuster_notes": None,
            }
        ]
        (claims_dir / f"{sample}.json").write_text(json.dumps(ground_truth), encoding="utf-8")
        (claims_dir / f"{sample}_canonical.md").write_text("# Page 1\n\nclean\n", encoding="utf-8")
        (claims_dir / f"{sample}_ocr.md").write_text("# Page 1\n\noisy\n", encoding="utf-8")
        (results_dir / f"{sample}_canonical_gemini_predicted.json").write_text(json.dumps(ground_truth), encoding="utf-8")
        (results_dir / f"{sample}_ocr_gemini_predicted.json").write_text(json.dumps([]), encoding="utf-8")

        results = run_evaluation_from_saved_predictions(
            models=["gemini"],
            samples=[sample],
            transcripts=["canonical", "ocr"],
            claims_dir=claims_dir,
            output_dir=results_dir,
        )

        self.assertEqual(len(results), 2)
        by_transcript = {result.transcript: result for result in results}
        self.assertEqual(by_transcript["canonical"].metrics["f1"], 1.0)
        self.assertEqual(by_transcript["ocr"].metrics["f1"], 0.0)

    def test_quick_mode_includes_extreme_sample(self) -> None:
        out_dir = Path(tempfile.mkdtemp())
        source_dir = Path(__file__).resolve().parents[1] / "benchmarks" / "results" / "local_two_regimes"
        for sample in [
            "easy_10_001_detailed",
            "medium_25_001_detailed",
            "hard_50_001_detailed",
            "extreme_100_001_detailed",
        ]:
            shutil.copyfile(
                source_dir / f"{sample}_gemini_predicted.json",
                out_dir / f"{sample}_gemini_predicted.json",
            )

        argv = [
            "evaluate_models.py",
            "--offline",
            "--quick",
            "--models",
            "gemini",
            "--output-dir",
            str(out_dir),
        ]

        with mock.patch("sys.argv", argv), mock.patch("sys.stdout", new_callable=io.StringIO):
            evaluate_models.main()

        report = json.loads((out_dir / "evaluation_report.json").read_text(encoding="utf-8"))
        samples = {entry["sample"] for entry in report["detailed_results"]}
        self.assertIn("extreme_100_001_detailed", samples)
        self.assertEqual(len(samples), 4)


if __name__ == "__main__":
    unittest.main()
