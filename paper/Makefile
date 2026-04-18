# Makefile for LaTeX paper compilation

# Main file name (without .tex extension)
MAIN = main

# LaTeX compiler
LATEX = pdflatex
BIBTEX = biber

# Compilation flags
LATEX_FLAGS = -interaction=nonstopmode -halt-on-error

ARXIV_DIR = arxiv_submission
ARXIV_TAR = arxiv_submission.tar.gz

.PHONY: all clean pdf view arxiv cleanarxiv

# Default target
all: pdf

# Compile the PDF
pdf:
	$(LATEX) $(LATEX_FLAGS) $(MAIN).tex
	$(BIBTEX) $(MAIN)
	$(LATEX) $(LATEX_FLAGS) $(MAIN).tex
	$(LATEX) $(LATEX_FLAGS) $(MAIN).tex

# Quick compile (single pass, no bibliography update)
quick:
	$(LATEX) $(LATEX_FLAGS) $(MAIN).tex

# Create a clean arXiv submission bundle
arxiv: pdf
	rm -rf $(ARXIV_DIR) $(ARXIV_TAR)
	mkdir -p $(ARXIV_DIR) $(ARXIV_DIR)/contents $(ARXIV_DIR)/figures
	cp $(MAIN).tex $(ARXIV_DIR)/
	cp references.bib $(ARXIV_DIR)/
	cp $(MAIN).bbl $(ARXIV_DIR)/
	cp contents/0_abstract.tex $(ARXIV_DIR)/contents/
	cp contents/1_introduction.tex $(ARXIV_DIR)/contents/
	cp contents/2_related_work.tex $(ARXIV_DIR)/contents/
	cp contents/4_methodology.tex $(ARXIV_DIR)/contents/
	cp contents/5_evaluation.tex $(ARXIV_DIR)/contents/
	cp contents/6_results.tex $(ARXIV_DIR)/contents/
	cp contents/7_limitations_and_future_directions.tex $(ARXIV_DIR)/contents/
	cp contents/8_conclusion.tex $(ARXIV_DIR)/contents/
	cp contents/appendix_schemas.tex $(ARXIV_DIR)/contents/
	find figures -maxdepth 1 -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.pdf' \) -exec cp {} $(ARXIV_DIR)/figures/ \;
	tar -czf $(ARXIV_TAR) -C $(ARXIV_DIR) .

cleanarxiv:
	rm -rf $(ARXIV_DIR) $(ARXIV_TAR)

# Clean auxiliary files
clean:
	rm -f *.aux *.log *.out *.toc *.bbl *.blg *.synctex.gz \
	      *.fdb_latexmk *.fls *.bcf *.run.xml *.xdv

# Clean everything including PDF
cleanall: clean
	rm -f $(MAIN).pdf

# View the PDF (macOS)
view: pdf
	open $(MAIN).pdf

# Help
help:
	@echo "Available targets:"
	@echo "  make          - Compile the PDF (full build with bibliography)"
	@echo "  make quick    - Quick compile (single pass, no bibliography)"
	@echo "  make clean    - Remove auxiliary files"
	@echo "  make cleanall - Remove all generated files including PDF"
	@echo "  make view     - Compile and open the PDF"
	@echo "  make help     - Show this help message"

