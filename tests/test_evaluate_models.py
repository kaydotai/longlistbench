import io
import json
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
from benchmarks.evaluation_metrics import evaluate_record_extraction


class EvaluatorRegressionTests(unittest.TestCase):
    def test_dataset_provenance_uses_repository_relative_manifest_path(self) -> None:
        provenance = evaluate_models._dataset_provenance()

        self.assertEqual(provenance["manifest_path"], "data/manifest.json")
        self.assertFalse(Path(provenance["manifest_path"]).is_absolute())

    @mock.patch.object(
        evaluate_models.subprocess,
        "check_output",
        return_value=(
            " M benchmarks/results/codex/evaluation_report.json\n"
            "?? benchmarks/results/claude/evaluation_report.md\n"
        ),
    )
    def test_git_dirty_ignores_generated_reports(self, _check_output) -> None:
        self.assertFalse(evaluate_models._git_dirty())

    @mock.patch.object(
        evaluate_models.subprocess,
        "check_output",
        return_value=" M benchmarks/evaluation_metrics.py\n",
    )
    def test_git_dirty_keeps_source_changes(self, _check_output) -> None:
        self.assertTrue(evaluate_models._git_dirty())

    def test_release_families_have_fixed_evaluation_roles(self) -> None:
        manifest_path = Path(__file__).resolve().parents[1] / "data" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        totals = {
            "scale_control": {"documents": 0, "records": 0},
            "structural_challenge": {"documents": 0, "records": 0},
        }

        for instance in manifest["instances"]:
            role = evaluate_models.evaluation_role(instance["complexity_regime"])
            self.assertNotEqual(role, "unclassified", instance["id"])
            totals[role]["documents"] += 1
            totals[role]["records"] += instance["num_target_records"]

        self.assertEqual(totals["scale_control"], {"documents": 13, "records": 21_185})
        self.assertEqual(
            totals["structural_challenge"],
            {"documents": 19, "records": 8_414},
        )

    def test_checker_reuses_main_evaluator_metrics_function(self) -> None:
        self.assertIs(
            check_evaluation_report.evaluate_extraction,
            evaluate_models.evaluate_extraction,
        )

    def test_checker_recomputes_strict_and_stressor_aggregates(self) -> None:
        claims_dir = Path(tempfile.mkdtemp())
        (claims_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "instances": [
                        {
                            "id": "scale-sample",
                            "complexity_regime": "ifta_mileage_by_vehicle",
                            "problems": ["page_breaks"],
                        },
                        {
                            "id": "structural-sample",
                            "complexity_regime": "policy_multi_hop",
                            "problems": ["long_range_evidence"],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        detailed_results = [
            {
                "model": "test_model",
                "sample": "scale-sample",
                "tier": "core_operations",
                "format": "pdf",
                "transcript": "ocr",
                "error": None,
                "metrics": {
                    "ground_truth_count": 2,
                    "predicted_count": 2,
                    "exact_record_matches": 2,
                    "complete_document": True,
                    "f1": 1.0,
                    "recall": 1.0,
                    "precision": 1.0,
                    "found": 4,
                    "total_gold_field_pairs": 4,
                    "total_pred_field_pairs": 4,
                },
            },
            {
                "model": "test_model",
                "sample": "structural-sample",
                "tier": "policy_packets",
                "format": "pdf",
                "transcript": "ocr",
                "error": None,
                "metrics": {
                    "ground_truth_count": 3,
                    "predicted_count": 4,
                    "exact_record_matches": 1,
                    "complete_document": False,
                    "f1": 0.5,
                    "recall": 0.5,
                    "precision": 0.5,
                    "found": 3,
                    "total_gold_field_pairs": 6,
                    "total_pred_field_pairs": 6,
                },
            },
        ]

        recomputed = check_evaluation_report._recompute_model_stats(
            detailed_results,
            claims_dir=claims_dir,
        )
        stats = recomputed["test_model"]

        self.assertEqual(stats["total_exact_record_matches"], 3)
        self.assertEqual(stats["exact_record_recall"], 3 / 5)
        self.assertEqual(stats["complete_documents"], 1)
        self.assertEqual(stats["complete_document_rate"], 0.5)
        self.assertEqual(
            stats["by_evaluation_role"]["scale_control"]["exact_record_recall"],
            1.0,
        )
        self.assertEqual(
            stats["by_stressor"]["long_range_evidence"]["exact_record_recall"],
            1 / 3,
        )

        tampered = json.loads(json.dumps(recomputed))
        tampered["test_model"]["by_stressor"]["long_range_evidence"][
            "exact_record_recall"
        ] = 1.0
        errors = check_evaluation_report._compare_model_stats(
            expected=tampered,
            actual=recomputed,
            tol=1e-12,
        )
        self.assertTrue(any("exact_record_recall mismatch" in error for error in errors))

    def test_checker_rejects_omitted_per_sample_metric(self) -> None:
        actual = {
            "ground_truth_count": 1,
            "predicted_count": 1,
            "exact_record_matches": 1,
            "exact_record_recall": 1.0,
        }
        expected = dict(actual)
        expected.pop("exact_record_recall")

        errors = check_evaluation_report._compare_metrics(
            sample="sample",
            model="model",
            expected=expected,
            actual=actual,
            tol=1e-12,
        )

        self.assertIn(
            "sample / model: report metrics missing key 'exact_record_recall'",
            errors,
        )

    def test_full_corpus_coverage_rejects_missing_and_duplicate_sample(self) -> None:
        detailed_results = [
            {"model": "model", "sample": "a", "transcript": "ocr"},
            {"model": "model", "sample": "a", "transcript": "ocr"},
        ]

        errors = check_evaluation_report._full_corpus_coverage_errors(
            detailed_results,
            manifest_instances=[{"id": "a"}, {"id": "b"}],
        )

        self.assertEqual(len(errors), 1)
        self.assertIn("missing=['b']", errors[0])
        self.assertIn("extra_or_duplicate=['a']", errors[0])

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

    def test_policy_record_evaluator_matches_without_hidden_ids(self) -> None:
        ground_truth = [
            {
                "record_type": "bop_coverage_item",
                "policy_number": "P-1",
                "named_insured": "Example LLC",
                "coverage": "Building",
                "location_number": "001",
                "building_number": "001",
                "limit": "$60,000",
                "premium": "$210",
            },
            {
                "record_type": "bop_coverage_item",
                "policy_number": "P-1",
                "named_insured": "Example LLC",
                "coverage": "Equipment Breakdown",
                "location_number": "002",
                "building_number": "001",
                "limit": "$125,000",
                "premium": "$292",
            },
        ]
        predicted = [
            {
                "record_type": "bop_coverage_item",
                "policy_number": "P-1",
                "named_insured": "Example LLC",
                "coverage": "Equipment Breakdown",
                "location_number": "002",
                "building_number": "001",
                "limit": "125000",
                "premium": "292",
            },
            {
                "record_type": "bop_coverage_item",
                "policy_number": "P-1",
                "named_insured": "Example LLC",
                "coverage": "Building",
                "location_number": "001",
                "building_number": "001",
                "limit": "60000",
                "premium": "$999",
            },
        ]

        metrics = evaluate_record_extraction(predicted, ground_truth)

        self.assertEqual(metrics["ground_truth_count"], 2)
        self.assertEqual(metrics["predicted_count"], 2)
        self.assertEqual(metrics["missing"], 0)
        self.assertEqual(metrics["extra"], 0)
        self.assertEqual(metrics["found"], 9)
        self.assertEqual(metrics["total_gold_field_pairs"], 10)
        self.assertAlmostEqual(metrics["f1"], 0.9)
        self.assertEqual(metrics["by_record_type"]["bop_coverage_item"]["matched_records"], 2)

    def test_policy_record_evaluator_does_not_require_record_type_association(self) -> None:
        ground_truth = [
            {
                "record_type": "policy_form_item",
                "policy_number": "P-1",
                "form_number": "BP 00 01",
                "form_title": "Businessowners Coverage Form",
            }
        ]
        predicted = [
            {
                "policy_number": "P-1",
                "form_number": "BP 00 01",
                "form_title": "Businessowners Coverage Form",
            }
        ]

        metrics = evaluate_record_extraction(predicted, ground_truth)

        self.assertEqual(metrics["found"], 2)
        self.assertEqual(metrics["missing"], 0)
        self.assertEqual(metrics["extra"], 0)
        self.assertEqual(metrics["f1"], 1.0)

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
                        "exact_record_matches": 1,
                        "complete_document": True,
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
                        "exact_record_matches": 0,
                        "complete_document": False,
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
        self.assertEqual(report["model_stats"]["gemini"]["exact_record_recall"], 0.5)
        self.assertEqual(report["model_stats"]["gemini"]["complete_documents"], 1)
        self.assertEqual(report["model_stats"]["gemini"]["complete_document_rate"], 0.5)

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
                        "exact_record_matches": 1,
                        "complete_document": True,
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

    def test_report_omits_missing_tier_and_format_slices(self) -> None:
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
                        "exact_record_matches": 1,
                        "complete_document": True,
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
        self.assertIn("| Model | Easy |", markdown)
        self.assertNotIn("| Model | Easy | Medium | Hard | Extreme |", markdown)
        self.assertIn("| Model | Detailed |", markdown)
        self.assertNotIn("| Model | Detailed | Table |", markdown)
        self.assertIn("| Model | Canonical | OCR |", markdown)
        self.assertIn("| Gemini Pro Preview | 100.0% | N/A |", markdown)

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

    def test_offline_evaluation_uses_generic_policy_record_scorer(self) -> None:
        dataset_dir = Path(tempfile.mkdtemp())
        results_dir = Path(tempfile.mkdtemp())
        (dataset_dir / "pdfs").mkdir(parents=True)
        (dataset_dir / "ground_truth").mkdir(parents=True)
        (dataset_dir / "transcripts" / "canonical").mkdir(parents=True)

        sample = "multihop_bop_012_001"
        records = [
            {
                "record_type": "policy_form_item",
                "policy_number": "P-1",
                "named_insured": "Example LLC",
                "form_number": "BP 00 01",
                "form_title": "Businessowners Coverage Form",
                "edition_date": "12 23",
            }
        ]
        (dataset_dir / "ground_truth" / f"{sample}.json").write_text(json.dumps(records), encoding="utf-8")
        (dataset_dir / "transcripts" / "canonical" / f"{sample}.md").write_text(
            "# Page 1\n\npolicy text\n",
            encoding="utf-8",
        )
        (results_dir / f"{sample}_canonical_fake_policy_predicted.json").write_text(
            json.dumps({"records": records}),
            encoding="utf-8",
        )

        fake_config = evaluate_models.ModelConfig(
            name="Fake Policy Extractor",
            provider="Test",
            model_id="fake-policy",
            setup_fn=lambda: object(),
            extract_fn=lambda *_: (_ for _ in ()).throw(AssertionError("offline should not extract")),
        )
        with mock.patch.dict(evaluate_models.MODELS, {"fake_policy": fake_config}):
            results = run_evaluation_from_saved_predictions(
                models=["fake_policy"],
                samples=[sample],
                transcripts=["canonical"],
                claims_dir=dataset_dir,
                output_dir=results_dir,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tier, "policy_packets")
        self.assertEqual(results[0].format, "crosspage")
        self.assertEqual(results[0].metrics["f1"], 1.0)
        self.assertIn("policy_form_item", results[0].metrics["by_record_type"])

    def test_offline_evaluation_preserves_saved_cost_metadata(self) -> None:
        claims_dir = Path(tempfile.mkdtemp())
        results_dir = Path(tempfile.mkdtemp())

        sample = "easy_10_001_detailed"
        incident = {
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
        model_key = "fake_agent"
        (claims_dir / f"{sample}.json").write_text(json.dumps([incident]), encoding="utf-8")
        (claims_dir / f"{sample}_ocr.md").write_text("# Page 1\n\noisy\n", encoding="utf-8")
        (results_dir / f"{sample}_ocr_{model_key}_predicted.json").write_text(json.dumps([incident]), encoding="utf-8")
        previous_report = results_dir / "previous_report.json"
        previous_report.write_text(
            json.dumps(
                {
                    "detailed_results": [
                        {
                            "model": model_key,
                            "sample": sample,
                            "transcript": "ocr",
                            "extraction_time": 12.5,
                            "tokens": {
                                "requests": 2,
                                "input_tokens": 100,
                                "cached_input_tokens": 25,
                                "output_tokens": 10,
                                "total_tokens": 110,
                            },
                            "cost_usd": 0.00123,
                            "error": None,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        fake_config = evaluate_models.ModelConfig(
            name="Fake Agent",
            provider="Test",
            model_id="fake-agent",
            setup_fn=lambda: object(),
            extract_fn=lambda *_: (_ for _ in ()).throw(AssertionError("offline should not extract")),
        )
        with mock.patch.dict(evaluate_models.MODELS, {model_key: fake_config}):
            results = run_evaluation_from_saved_predictions(
                models=[model_key],
                samples=[sample],
                transcripts=["ocr"],
                claims_dir=claims_dir,
                output_dir=results_dir,
                previous_report_path=previous_report,
            )

        self.assertEqual(results[0].extraction_time, 12.5)
        self.assertEqual(results[0].tokens["input_tokens"], 100)
        self.assertEqual(results[0].cost_usd, 0.00123)

    def test_saved_evaluation_loads_bonsai_run_metadata(self) -> None:
        results_dir = Path(tempfile.mkdtemp())
        sample = "driver_mvr_packet_001"
        model_key = "bonsai_27b_together_page_pipeline"
        (results_dir / "run_metadata.json").write_text(
            json.dumps(
                {
                    "model_key": model_key,
                    "transcript": "ocr",
                    "samples": {
                        sample: {
                            "sample": sample,
                            "transcript": "ocr",
                            "extraction_time": 12.5,
                            "prompt_tokens": 100,
                            "completion_tokens": 25,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        metadata = evaluate_models._load_saved_result_metadata(
            output_dir=results_dir,
        )

        self.assertEqual(
            metadata[(sample, "ocr", model_key)],
            {
                "extraction_time": 12.5,
                "tokens": {
                    "input_tokens": 100,
                    "output_tokens": 25,
                    "total_tokens": 125,
                },
            },
        )

    def test_resume_preserves_saved_cost_metadata(self) -> None:
        claims_dir = Path(tempfile.mkdtemp())
        results_dir = Path(tempfile.mkdtemp())

        sample = "easy_10_001_detailed"
        incident = {
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
        model_key = "fake_agent"
        (claims_dir / f"{sample}.json").write_text(json.dumps([incident]), encoding="utf-8")
        (claims_dir / f"{sample}_ocr.md").write_text("# Page 1\n\noisy\n", encoding="utf-8")
        (results_dir / f"{sample}_ocr_{model_key}_predicted.json").write_text(json.dumps([incident]), encoding="utf-8")
        (results_dir / "evaluation_report.json").write_text(
            json.dumps(
                {
                    "detailed_results": [
                        {
                            "model": model_key,
                            "sample": sample,
                            "transcript": "ocr",
                            "extraction_time": 8.0,
                            "tokens": {
                                "requests": 1,
                                "input_tokens": 50,
                                "cached_input_tokens": 5,
                                "output_tokens": 7,
                                "total_tokens": 57,
                            },
                            "cost_usd": 0.00089,
                            "error": None,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        fake_config = evaluate_models.ModelConfig(
            name="Fake Agent",
            provider="Test",
            model_id="fake-agent",
            setup_fn=lambda: object(),
            extract_fn=lambda *_: (_ for _ in ()).throw(AssertionError("resume should not extract")),
        )
        pred_path = results_dir / f"{sample}_ocr_{model_key}_predicted.json"
        provenance = evaluate_models._online_input_provenance(
            entry=evaluate_models.EvaluationInput(
                sample=sample,
                tier="easy",
                format="detailed",
                transcript="ocr",
            ),
            config=fake_config,
            model_key=model_key,
            transcript_text=(claims_dir / f"{sample}_ocr.md").read_text(encoding="utf-8"),
            ground_truth=[incident],
        )
        provenance_key = evaluate_models._prediction_provenance_key(sample, "ocr", model_key)
        evaluate_models._write_prediction_provenance(
            results_dir,
            {
                provenance_key: evaluate_models._bind_online_prediction_provenance(
                    provenance,
                    pred_path,
                )
            },
        )
        with mock.patch.dict(evaluate_models.MODELS, {model_key: fake_config}):
            results = evaluate_models.run_evaluation(
                models=[model_key],
                samples=[sample],
                transcripts=["ocr"],
                claims_dir=claims_dir,
                output_dir=results_dir,
                resume=True,
            )

        self.assertEqual(results[0].extraction_time, 8.0)
        self.assertEqual(results[0].tokens["output_tokens"], 7)
        self.assertEqual(results[0].cost_usd, 0.00089)

    def test_online_resume_rejects_changed_prediction(self) -> None:
        output_dir = Path(tempfile.mkdtemp())
        pred_path = output_dir / "sample_ocr_fake_predicted.json"
        pred_path.write_text("[]", encoding="utf-8")
        expected = {"input_fingerprint_sha256": "abc"}
        saved = evaluate_models._bind_online_prediction_provenance(expected, pred_path)

        self.assertTrue(evaluate_models._online_resume_matches(saved, expected, pred_path))
        pred_path.write_text("[{}]", encoding="utf-8")
        self.assertFalse(evaluate_models._online_resume_matches(saved, expected, pred_path))

    def test_quick_mode_uses_current_release_samples(self) -> None:
        out_dir = Path(tempfile.mkdtemp())
        dataset_dir = evaluate_models.default_dataset_dir()
        for sample in evaluate_models._QUICK_SAMPLES:
            ground_truth = (dataset_dir / "ground_truth" / f"{sample}.json").read_text(encoding="utf-8")
            (out_dir / f"{sample}_ocr_gemini_predicted.json").write_text(ground_truth, encoding="utf-8")

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
        self.assertEqual(samples, set(evaluate_models._QUICK_SAMPLES))

    def test_cli_model_choices_follow_model_registry(self) -> None:
        parser = evaluate_models.build_argument_parser()

        args = parser.parse_args(["--models", "codex_gpt56_sol", "claude_fable5"])

        self.assertEqual(args.models, ["codex_gpt56_sol", "claude_fable5"])
        models_action = next(action for action in parser._actions if action.dest == "models")
        self.assertEqual(set(models_action.choices), set(evaluate_models.MODELS))


if __name__ == "__main__":
    unittest.main()
