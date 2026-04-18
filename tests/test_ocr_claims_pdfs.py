import unittest

from benchmarks.ocr_claims_pdfs import build_arg_parser


class OcrCliTests(unittest.TestCase):
    def test_default_ocr_engine_is_gemini(self) -> None:
        parser = build_arg_parser()
        args = parser.parse_args([])
        self.assertEqual(args.ocr_engine, "gemini")


if __name__ == "__main__":
    unittest.main()
