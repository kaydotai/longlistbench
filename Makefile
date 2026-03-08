# Repository Makefile (convenience targets)

.PHONY: help setup generate ocr eval paper paper-quick clean

VENV_DIR ?= .venv
EVAL_OUT ?= benchmarks/results/scratch/eval_ocr100

help:
	@echo "Targets:"
	@echo "  make setup       - Create .venv + install benchmark deps + install Playwright Chromium"
	@echo "  make generate    - Generate the synthetic benchmark dataset (PDF/HTML/JSON)"
	@echo "  make ocr         - OCR all generated PDFs (requires GEMINI_API_KEY)"
	@echo "  make eval        - Run evaluation (requires model API keys unless --offline)"
	@echo "  make paper       - Build the paper PDF (full build with bibliography)"
	@echo "  make paper-quick - Quick paper build (single pass, no bibliography update)"
	@echo "  make clean       - Clean paper build artifacts"

setup:
	python3 -m venv $(VENV_DIR)
	. $(VENV_DIR)/bin/activate && python -m pip install -r benchmarks/requirements.txt
	. $(VENV_DIR)/bin/activate && python -m playwright install chromium

generate:
	. $(VENV_DIR)/bin/activate && python benchmarks/generate_claims_benchmark.py

ocr:
	. $(VENV_DIR)/bin/activate && python benchmarks/ocr_claims_pdfs.py

eval:
	. $(VENV_DIR)/bin/activate && python benchmarks/evaluate_models.py --models gemini gpt52 --parallel-models --model-workers 2 --output-dir $(EVAL_OUT)

paper:
	$(MAKE) -C paper pdf

paper-quick:
	$(MAKE) -C paper quick

clean:
	$(MAKE) -C paper clean
