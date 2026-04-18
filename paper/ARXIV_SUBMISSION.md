# arXiv Submission Guide

This document describes the release workflow for the LongListBench paper in this repository.

## Release Checklist

Before uploading to arXiv, confirm the following:

- The paper compiles locally with `make`
- `main.pdf` has been visually checked after the final build
- Title, authors, affiliation, and PDF metadata in `main.tex` are final
- The abstract and manuscript contain no placeholder text or draft notes
- All figures are local files in `paper/figures/` and use PDFLaTeX-safe formats (`.png`, `.jpg`, `.pdf`)
- The submission is single-spaced, 12pt, US Letter, and has at least 1-inch margins
- The paper contains no line numbers, referee mode, margin notes, or obstructive watermarks
- Any code/data links in the paper resolve to a public repository at submission time

## Files to Include

For this paper, the arXiv source bundle should include:

```text
main.tex
main.bbl
references.bib
contents/
figures/
```

The `contents/` directory should include the actual section files used by `main.tex`, including:

```text
contents/0_abstract.tex
contents/1_introduction.tex
contents/2_related_work.tex
contents/4_methodology.tex
contents/5_evaluation.tex
contents/6_results.tex
contents/7_limitations_and_future_directions.tex
contents/8_conclusion.tex
contents/appendix_schemas.tex
```

## Files to Exclude

Do not upload build artifacts or editor files such as:

```text
main.pdf
*.aux
*.log
*.out
*.blg
*.run.xml
*.synctex.gz
.DS_Store
```

## Bibliography Note

This project uses `biblatex` with the `biber` backend. arXiv can detect `biblatex` and select the configured backend, but the safest workflow for this repository is:

- compile locally first
- include `main.bbl` in the submission bundle
- also include `references.bib`

Best practice is to keep `main.tex` and `main.bbl` synchronized by generating both from the same local build immediately before packaging.

## Recommended Workflow

From `paper/`:

```bash
make
make arxiv
```

This will:

- rebuild the PDF
- create `paper/arxiv_submission/`
- create `paper/arxiv_submission.tar.gz`

## Manual Verification Before Upload

After `make arxiv`, verify:

- `arxiv_submission/main.tex` exists
- `arxiv_submission/main.bbl` exists
- `arxiv_submission/references.bib` exists
- `arxiv_submission/contents/` contains the section files referenced by `main.tex`
- `arxiv_submission/figures/` contains every figure used by the manuscript

If arXiv asks which source file is the entry point, select `main.tex`.

## Submission Notes

- Suggested categories are likely in the document-understanding / information-extraction area (for example `cs.AI` or `cs.CL`), but choose the final category manually at submission time.
- Paste the abstract from `contents/0_abstract.tex` into the arXiv metadata form.
- Add a short comment such as `18 pages, 5 figures` if desired.
- Avoid adding copyright language that conflicts with arXiv redistribution.

## If Something Fails on arXiv

### Bibliography issue

- Rebuild locally with `make`
- Regenerate the package with `make arxiv`
- Make sure `main.bbl` is present and matches the current manuscript build

### Missing figure

- Ensure the figure path is relative (for example `figures/generation.png`)
- Ensure the file is present inside `arxiv_submission/figures/`

### Package or compilation issue

- Prefer standard TeX Live packages only
- Remove any local-only or unusual package if arXiv rejects it
- Rebuild locally and inspect `main.log` before repackaging

## Useful References

- arXiv TeX submission guide: https://info.arxiv.org/help/submit_tex.html
- arXiv format requirements: https://info.arxiv.org/help/policies/format_requirements.html
- arXiv submission help: https://info.arxiv.org/help/submit/index.html

