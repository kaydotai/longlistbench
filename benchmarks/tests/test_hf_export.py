import json
import tempfile
import unittest
from pathlib import Path

from benchmarks import export_hf_dataset


class HuggingFaceExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        for relative in [
            "ground_truth",
            "pdfs",
            "transcripts/ocr_gemini",
            "schemas",
        ]:
            (self.data_dir / relative).mkdir(parents=True, exist_ok=True)
        (self.data_dir / "schemas" / "loss_run_incident.schema.json").write_text(
            '{"title":"LossRunIncident","type":"object"}',
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _write_instance(self, instance):
        sample_id = instance["id"]
        target_records = [{"id": sample_id, "value": "expected"}]
        (self.data_dir / "ground_truth" / f"{sample_id}.json").write_text(
            json.dumps(target_records),
            encoding="utf-8",
        )
        (self.data_dir / "pdfs" / f"{sample_id}.pdf").write_bytes(b"%PDF-1.4\n")
        if "ocr" in instance.get("transcripts_available", []):
            (self.data_dir / "transcripts" / "ocr_gemini" / f"{sample_id}.md").write_text(
                f"ocr {sample_id}",
                encoding="utf-8",
            )
        instance["files"] = {
            "ground_truth": f"ground_truth/{sample_id}.json",
            "pdf": f"pdfs/{sample_id}.pdf",
            "ocr_md": f"transcripts/ocr_gemini/{sample_id}.md",
        }
        return instance

    def test_build_config_rows_normalizes_manifest_instances(self):
        instances = [
            self._write_instance(
                {
                    "id": "ifta_mileage_by_vehicle_001",
                    "difficulty": "ifta_mileage_by_vehicle",
                    "format": "production_like_pdf",
                    "domain": "commercial_insurance_operations",
                    "target_record_type": "vehicle_state_mileage_row",
                    "num_target_records": 1,
                    "pages_estimate": 8,
                    "problems": ["high_density_long_list"],
                    "transcripts_available": ["ocr"],
                }
            ),
            self._write_instance(
                {
                    "id": "multihop_012_001_crosspage",
                    "complexity_regime": "claim_crosspage_multihop",
                    "difficulty": "multihop",
                    "format": "crosspage",
                    "domain": "claims",
                    "target_record_type": "loss_run_incident",
                    "num_target_records": 1,
                    "pdf_page_count": 76,
                    "problems": ["cross_page_join"],
                    "transcripts_available": ["ocr"],
                }
            ),
            self._write_instance(
                {
                    "id": "multihop_bop_012_001",
                    "complexity_regime": "policy_multi_hop",
                    "difficulty": "multihop",
                    "format": "crosspage",
                    "domain": "policy_review",
                    "target_record_type": "policy_packet_item",
                    "num_target_records": 1,
                    "pdf_page_count": 90,
                    "problems": ["businessowners_policy"],
                    "transcripts_available": ["ocr"],
                }
            ),
        ]
        (self.data_dir / "manifest.json").write_text(
            json.dumps({"instances": instances}),
            encoding="utf-8",
        )

        rows_by_config = export_hf_dataset.build_config_rows(self.data_dir)

        self.assertEqual(
            [row["document_id"] for row in rows_by_config["core_operations"]],
            ["ifta_mileage_by_vehicle_001"],
        )
        self.assertEqual(
            [row["document_id"] for row in rows_by_config["claim_multihop"]],
            ["multihop_012_001_crosspage"],
        )
        self.assertEqual(
            [row["document_id"] for row in rows_by_config["policy_packets"]],
            ["multihop_bop_012_001"],
        )

        core_row = rows_by_config["core_operations"][0]
        self.assertEqual(core_row["complexity_regime"], "ifta_mileage_by_vehicle")
        self.assertEqual(core_row["evaluation_role"], "scale_control")
        self.assertEqual(core_row["stressors"], ["high_density_long_list"])
        for removed in ("domain", "difficulty", "document_format", "transcript_conditions", "problems"):
            self.assertNotIn(removed, core_row)
        self.assertEqual(core_row["target_field"], "records")
        self.assertEqual(json.loads(core_row["ground_truth"])["records"][0]["id"], "ifta_mileage_by_vehicle_001")
        self.assertEqual(core_row["ocr_transcript"], "ocr ifta_mileage_by_vehicle_001")

        policy_row = rows_by_config["policy_packets"][0]
        self.assertEqual(policy_row["target_field"], "records")
        self.assertEqual(policy_row["evaluation_role"], "structural_challenge")
        self.assertEqual(policy_row["target_record_type"], "policy_packet_item")
        self.assertEqual(json.loads(policy_row["ground_truth"])["records"][0]["id"], "multihop_bop_012_001")
        self.assertEqual(policy_row["ocr_transcript"], "ocr multihop_bop_012_001")

    def test_parquet_export_round_trips_published_schema(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        instance = self._write_instance(
            {
                "id": "ifta_mileage_by_vehicle_001",
                "difficulty": "ifta_mileage_by_vehicle",
                "format": "production_like_pdf",
                "domain": "commercial_insurance_operations",
                "target_record_type": "vehicle_state_mileage_row",
                "num_target_records": 1,
                "pages_estimate": 8,
                "problems": ["high_density_long_list"],
                "transcripts_available": ["ocr"],
            }
        )
        (self.data_dir / "manifest.json").write_text(
            json.dumps({"instances": [instance]}),
            encoding="utf-8",
        )
        rows_by_config = export_hf_dataset.build_config_rows(self.data_dir)
        output_dir = Path(self.tmp.name) / "hf-export"

        export_hf_dataset.write_parquet_export(rows_by_config, output_dir)

        table = pq.read_table(
            output_dir / "data" / "core_operations" / "test-00000-of-00001.parquet"
        )
        self.assertEqual(
            table.column_names,
            [
                "document_id",
                "complexity_regime",
                "evaluation_role",
                "num_pages",
                "target_field",
                "target_record_type",
                "target_count",
                "stressors",
                "pdf",
                "ground_truth",
                "metadata",
                "ocr_transcript",
            ],
        )
        self.assertEqual(table.schema.field("num_pages").type, pa.int32())
        self.assertEqual(table.schema.field("target_count").type, pa.int32())
        self.assertEqual(table.schema.field("stressors").type, pa.list_(pa.string()))
        self.assertEqual(table.column("stressors")[0].as_py(), ["high_density_long_list"])
        metadata = json.loads(table.column("metadata")[0].as_py())
        self.assertEqual(
            metadata["manifest_instance"]["domain"],
            "commercial_insurance_operations",
        )

    def test_dataset_card_lists_hf_config_paths(self):
        summary = {
            "core_operations": {
                "rows": 26,
                "targets": 28178,
                "min_targets": 260,
                "max_targets": 2571,
                "min_pages": 17,
                "max_pages": 84,
                "target_fields": ["records"],
            },
            "claim_multihop": {
                "rows": 3,
                "targets": 77,
                "min_targets": 12,
                "max_targets": 40,
                "min_pages": 61,
                "max_pages": 148,
                "target_fields": ["incidents"],
            },
            "policy_packets": {
                "rows": 3,
                "targets": 1344,
                "min_targets": 344,
                "max_targets": 562,
                "min_pages": 99,
                "max_pages": 133,
                "target_fields": ["records"],
            },
        }

        regime_stats = {
            key: {
                "count": 1,
                "rows": 10,
                "weighted_f1": 0.9765933643324127,
                "exact_record_recall": 0.8,
            }
            for key, _ in export_hf_dataset.BASELINE_REGIMES
        }
        codex_role_stats = {
            "structural_challenge": {"count": 19, "rows": 8414, "exact_record_recall": 0.6757784645},
            "scale_control": {"count": 13, "rows": 21185, "exact_record_recall": 0.9948548501},
        }
        claude_role_stats = {
            "structural_challenge": {"count": 19, "rows": 8414, "exact_record_recall": 0.7928452579},
            "scale_control": {"count": 13, "rows": 21185, "exact_record_recall": 0.9930611282},
        }
        codex_baseline = {
            "report_path": Path("results/codex_full_current_ocr_v2/evaluation_report.json"),
            "model_key": "codex_gpt55",
            "presentation": export_hf_dataset.BASELINE_PRESENTATIONS["codex_gpt55"],
            "report": {"timestamp": "2026-07-01T12:04:51+00:00"},
            "model_stats": {
                "total_samples": 32,
                "total_rows": 29599,
                "errors": 0,
                "exact_record_recall": 0.9041521673,
                "complete_documents": 4,
                "complete_document_rate": 0.125,
                "weighted_f1": 0.9824580058,
                "avg_f1": 0.9767887730,
                "weighted_recall": 0.9729906733,
                "weighted_precision": 0.9921049740,
                "by_complexity_regime": regime_stats,
                "by_evaluation_role": codex_role_stats,
            },
        }
        claude_baseline = {
            "report_path": Path("results/claude_opus48_full_current_ocr_v2/evaluation_report.json"),
            "model_key": "claude_opus48",
            "presentation": export_hf_dataset.BASELINE_PRESENTATIONS["claude_opus48"],
            "report": {"timestamp": "2026-07-12T18:18:20+00:00"},
            "model_stats": {
                "total_samples": 32,
                "total_rows": 29599,
                "errors": 0,
                "exact_record_recall": 0.9361464914,
                "complete_documents": 7,
                "complete_document_rate": 0.21875,
                "weighted_f1": 0.9884245464,
                "avg_f1": 0.9839519696,
                "weighted_recall": 0.9790179660,
                "weighted_precision": 0.9980145540,
                "by_complexity_regime": regime_stats,
                "by_evaluation_role": claude_role_stats,
            },
        }

        card = export_hf_dataset.dataset_card(
            "kaydotai/LongListBench",
            summary,
            [codex_baseline, claude_baseline],
        )

        self.assertIn("pretty_name: LongListBench", card)
        self.assertIn("- benchmark", card)
        self.assertIn("- trucking", card)
        self.assertIn("path: data/core_operations/test-*.parquet", card)
        self.assertIn("Developed by [Kay.ai](https://kay.ai)", card)
        self.assertIn("[Anton Fedoruk](https://orcid.org/0009-0004-0260-1704)", card)
        self.assertIn("[Serhii Shchoholiev](https://orcid.org/0009-0007-2014-4828)", card)
        self.assertIn("[Akhil Mehta](https://orcid.org/0009-0001-0134-2905)", card)
        self.assertIn("and Vishal Rohra", card)
        self.assertIn("[Release v2.2.1]", card)
        self.assertIn(
            "[Leaderboard](https://huggingface.co/spaces/kaydotai/LongListBench-Leaderboard)",
            card,
        )
        self.assertNotIn("[Paper source]", card)
        self.assertIn("Records/doc range", card)
        self.assertIn("| `core_operations` |", card)
        self.assertIn("| 26 | 260-2,571 | 28,178 | 17-84 |", card)
        self.assertIn('load_dataset("kaydotai/LongListBench", "core_operations", split="test")', card)
        self.assertIn("Pdf(decode=False)", card)
        self.assertIn("## Canonical Scoring", card)
        self.assertIn("git clone --branch v2.2.1", card)
        self.assertIn("python -m pip install -r benchmarks/requirements-hf.txt", card)
        self.assertIn('"pydantic>=2.5.0"', card)
        self.assertIn("Run the scoring example from the repository root", card)
        self.assertIn("evaluate_record_extraction", card)
        self.assertIn("schemas/policy_packet_item.schema.json", card)
        self.assertIn("schemas/loss_run_claim_row.schema.json", card)
        self.assertIn("schemas/ifta_multisection_jurisdiction_row.schema.json", card)
        self.assertIn("@misc{fedoruk2026longlistbench", card)
        self.assertIn("and Rohra, Vishal", card)
        self.assertIn("publisher    = {Kay.ai}", card)
        self.assertIn("url          = {https://huggingface.co/datasets/kaydotai/LongListBench}", card)
        self.assertIn("| `policy_packets` |", card)
        self.assertIn("The release contains 32 synthetic PDFs and 29,599 target records", card)
        self.assertIn(
            "Across the 2 released agent runs, field micro-F1 ranges from 98.2% to 98.8%, "
            "but only 4-7 of 32 documents are complete.",
            card,
        )
        self.assertEqual(
            export_hf_dataset._headline_finding(codex_baseline),
            "Across the 1 released agent run, field micro-F1 is 98.2%, "
            "but only 4 of 32 documents are complete.",
        )
        self.assertIn("90.4% | 4/32 (12.5%) | 98.2% | 97.7%", card)
        self.assertIn("93.6% | 7/32 (21.9%) | 98.8% | 98.4%", card)
        self.assertIn("GPT-5.5 exact records | Opus 4.8 exact records", card)
        self.assertIn("Structural challenges", card)
        self.assertIn("Saved predictions and reports", card)
        self.assertIn("Gemini 3.5 Flash", card)
        self.assertIn("direct Vertex AI API", card)
        self.assertNotIn("- large-array", card)
        self.assertNotIn("**Shape.**", card)
        self.assertEqual(card.count("Record order is not scored"), 1)
        self.assertNotIn("\n\n\n## Schemas", card)
        self.assertNotIn("packages the fixed HTML, PDF", card)

    def test_default_release_baselines_include_all_four_agent_runs(self):
        self.assertEqual(len(export_hf_dataset.DEFAULT_BASELINE_REPORTS), 4)
        self.assertEqual(
            {path.parent.name for path in export_hf_dataset.DEFAULT_BASELINE_REPORTS},
            {
                "codex_gpt56_sol_full_current_ocr_v2",
                "claude_fable5_full_current_ocr_v2",
                "codex_full_current_ocr_v2",
                "claude_opus48_full_current_ocr_v2",
            },
        )

    def test_hf_requirements_include_evaluator_dependencies(self):
        requirements = (
            Path(export_hf_dataset.__file__).parent / "requirements-hf.txt"
        ).read_text(encoding="utf-8")

        self.assertIn("pydantic>=2.5.0", requirements.splitlines())

    def test_release_baseline_requires_matching_manifest_and_predictions(self):
        (self.data_dir / "manifest.json").write_text(
            json.dumps({"instances": []}),
            encoding="utf-8",
        )
        results_dir = Path(self.tmp.name) / "results" / "codex_full_current_ocr_v2"
        results_dir.mkdir(parents=True)
        report_path = results_dir / "evaluation_report.json"
        report = {
            "timestamp": "2026-07-01T12:04:51+00:00",
            "dataset": {
                "manifest_sha256": export_hf_dataset.sha256_file(self.data_dir / "manifest.json")
            },
            "model_stats": {export_hf_dataset.BASELINE_MODEL_KEY: {}},
            "detailed_results": [
                {
                    "sample": "sample_001",
                    "transcript": "ocr",
                    "model": export_hf_dataset.BASELINE_MODEL_KEY,
                    "error": None,
                }
            ],
        }
        report_path.write_text(json.dumps(report), encoding="utf-8")
        prediction = results_dir / "sample_001_ocr_codex_gpt55_predicted.json"
        prediction.write_text("[]", encoding="utf-8")

        baseline = export_hf_dataset.load_release_baseline(report_path, self.data_dir)
        claude_results_dir = Path(self.tmp.name) / "results" / "claude_opus48_full_current_ocr_v2"
        claude_results_dir.mkdir(parents=True)
        claude_report_path = claude_results_dir / "evaluation_report.json"
        claude_report = {
            "timestamp": "2026-07-12T18:18:20+00:00",
            "dataset": {
                "manifest_sha256": export_hf_dataset.sha256_file(self.data_dir / "manifest.json")
            },
            "model_stats": {"claude_opus48": {}},
            "detailed_results": [
                {
                    "sample": "sample_001",
                    "transcript": "ocr",
                    "model": "claude_opus48",
                    "error": None,
                }
            ],
        }
        claude_report_path.write_text(json.dumps(claude_report), encoding="utf-8")
        claude_prediction = claude_results_dir / "sample_001_ocr_claude_opus48_predicted.json"
        claude_prediction.write_text("[]", encoding="utf-8")
        claude_baseline = export_hf_dataset.load_release_baseline(
            claude_report_path,
            self.data_dir,
        )
        output_dir = Path(self.tmp.name) / "hf"
        export_hf_dataset.write_evaluation_files([baseline, claude_baseline], output_dir)

        self.assertTrue(
            (output_dir / "evaluation" / "codex_full_current_ocr_v2" / prediction.name).exists()
        )
        self.assertEqual(
            (
                output_dir
                / "evaluation"
                / "codex_full_current_ocr_v2"
                / "per_sample_status.tsv"
            ).read_text(encoding="utf-8"),
            "sample\tstatus\nsample_001\t0\n",
        )
        self.assertTrue(
            (
                output_dir
                / "evaluation"
                / "claude_opus48_full_current_ocr_v2"
                / claude_prediction.name
            ).exists()
        )

        report["dataset"]["manifest_sha256"] = "stale"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest hash does not match"):
            export_hf_dataset.load_release_baseline(report_path, self.data_dir)


if __name__ == "__main__":
    unittest.main()
