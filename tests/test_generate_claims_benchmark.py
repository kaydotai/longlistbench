import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.generate_claims_benchmark import rebuild_metadata


class GenerateClaimsBenchmarkTests(unittest.TestCase):
    def test_rebuild_metadata_only_advertises_available_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            sample = "easy_10_001_detailed"
            (out_dir / f"{sample}.json").write_text("[]", encoding="utf-8")
            (out_dir / f"{sample}.html").write_text("<html><body><div class='header'>x</div></body></html>", encoding="utf-8")
            (out_dir / f"{sample}.pdf").write_bytes(b"%PDF-1.4\n")

            metadata = rebuild_metadata(out_dir, base_seed=42)
            self.assertEqual(metadata["transcript_conditions"], ["canonical"])

            (out_dir / f"{sample}_ocr.md").write_text("# Page 1\n\nocr\n", encoding="utf-8")
            metadata = rebuild_metadata(out_dir, base_seed=42)
            self.assertEqual(metadata["transcript_conditions"], ["canonical", "ocr"])

            saved = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8")) if (out_dir / "metadata.json").exists() else None
            self.assertIsNone(saved)


if __name__ == "__main__":
    unittest.main()
