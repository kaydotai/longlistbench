# Research Paper

This directory contains the LaTeX source files for the research paper.

## Structure

- `main.tex` - Main LaTeX document with the paper structure
- `references.bib` - Bibliography file in BibTeX format
- `Makefile` - Build automation for compiling the paper

## Prerequisites

To compile the paper, you need a LaTeX distribution installed:

### macOS
```bash
brew install --cask mactex
```

## Compilation

### Using Make (Recommended)
```bash
# Full compilation with bibliography
make

# Quick compilation (single pass)
make quick

# Compile and view PDF
make view

# Clean auxiliary files
make clean

# Clean everything including PDF
make cleanall
```

### Manual Compilation
```bash
pdflatex main.tex
biber main
pdflatex main.tex
pdflatex main.tex
```

## Output

The compiled PDF will be generated as `main.pdf` in the same directory.

## Tips

1. **Editing**: Use a LaTeX editor like [TeXShop](https://pages.uoregon.edu/koch/texshop/) (macOS), [TeXstudio](https://www.texstudio.org/) (cross-platform), or [Overleaf](https://www.overleaf.com/) (online).

2. **Bibliography**: Add your references to `references.bib` in BibTeX format. You can use tools like [Google Scholar](https://scholar.google.com/) to generate BibTeX entries.

3. **Images**: Store images in a separate `figures/` directory and reference them in the LaTeX document using `\includegraphics{figures/image.pdf}`.

4. **Sections**: For longer papers, consider splitting sections into separate `.tex` files and using `\input{section_name.tex}` in the main document.

## Troubleshooting

- If compilation fails, check the `.log` file for error messages
- Ensure all required LaTeX packages are installed
- Run `make clean` if you encounter persistent errors
- For bibliography issues, ensure you're using `biber` (not `bibtex`) as specified in the preamble

