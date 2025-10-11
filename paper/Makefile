# Makefile for LaTeX paper compilation

# Main file name (without .tex extension)
MAIN = main

# LaTeX compiler
LATEX = pdflatex
BIBTEX = biber

# Compilation flags
LATEX_FLAGS = -interaction=nonstopmode -halt-on-error

.PHONY: all clean pdf view

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

