# arXiv Submission Guide

This document explains how to prepare and submit your paper to arXiv.

## Pre-Submission Checklist

### ✅ Document Requirements

- [x] Font size: 12pt (within 10-14pt range)
- [x] Paper size: US Letter (not A4)
- [x] Margins: 1 inch on all sides
- [x] Spacing: Single-spaced (arXiv standard)
- [x] No line numbers, watermarks, or margin notes
- [x] Complete references included

### ✅ File Requirements

- [x] LaTeX source files (`.tex`)
- [x] Bibliography file (`.bib`)
- [x] All figures included (not external links)
- [ ] Figures in correct format:
  - For LaTeX: PostScript (`.ps`, `.eps`)
  - For PDFLaTeX: JPEG, PNG, or PDF
- [x] Valid file names (only: `a-z A-Z 0-9 _ + - . , =`)

### ✅ Metadata

- [ ] Update title in `main.tex`
- [ ] Update author names and affiliations
- [ ] Update PDF metadata in hyperref setup
- [ ] Update keywords in hyperref setup
- [ ] Ensure abstract is concise (no "Abstract" heading needed)

## Files to Submit to arXiv

Include these files in your submission:

```
main.tex                    - Main document
references.bib              - Bibliography
contents/                   - Section content files
  ├── abstract.tex          - Abstract content
  ├── introduction.tex      - Introduction content
  ├── conclusion.tex        - Conclusion content
  └── acknowledgments.tex   - Acknowledgments content
[figures/]                  - Directory with all figures (if any)
```

**DO NOT include:**
- `main.pdf` (arXiv will generate this)
- Build files: `.aux`, `.log`, `.out`, `.bbl`, `.blg`, etc.
- `Makefile` (optional, but not required)
- `.gitignore`

## Preparing Your Submission

### Step 1: Update Metadata

Edit `main.tex` and update:

```latex
% Update these fields:
\title{Your Actual Paper Title}
\author{
    First Author\textsuperscript{1} \and
    Second Author\textsuperscript{2}
}

% Update PDF metadata in hyperref:
\hypersetup{
    pdfauthor={First Author, Second Author},
    pdftitle={Your Actual Paper Title},
    pdfsubject={Your research area},
    pdfkeywords={keyword1, keyword2, keyword3},
}
```

### Step 2: Add Figures (if any)

Create a `figures/` directory and add your images:

```bash
mkdir figures
# Copy your figures here
```

In your `.tex` files, reference figures:

```latex
\begin{figure}[htbp]
    \centering
    \includegraphics[width=0.8\linewidth]{figures/your_figure.pdf}
    \caption{Your figure caption}
    \label{fig:your_label}
\end{figure}
```

### Step 3: Clean and Test Compilation

```bash
# Clean previous builds
make cleanall

# Fresh compilation
make

# Verify the PDF looks correct
open main.pdf
```

### Step 4: Create Submission Package

Create a directory with only submission files:

```bash
# Create submission directory
mkdir arxiv_submission
cd arxiv_submission

# Copy required files
cp ../main.tex .
cp ../references.bib .
cp -r ../contents .

# If you have figures:
cp -r ../figures .

# Create a tarball (arXiv accepts .tar.gz)
cd ..
tar -czf arxiv_submission.tar.gz arxiv_submission/
```

## Submission Process

### 1. Register/Login to arXiv
- Visit: https://arxiv.org/user/login
- Create account if needed

### 2. Start New Submission
- Go to: https://arxiv.org/submit
- Click "START NEW SUBMISSION"

### 3. Upload Files
- Choose "Upload files" option
- Upload your `.tar.gz` file OR individual files
- arXiv will process and compile your submission

### 4. Add Metadata
- Select category (e.g., cs.AI, cs.LG, stat.ML)
- Verify title and authors match your document
- Add abstract (copy from `abstract.tex`)
- Add comments (optional, e.g., "10 pages, 3 figures")

### 5. Preview and Submit
- Review the compiled PDF
- Check for any compilation errors or warnings
- If satisfied, submit for moderation

## arXiv Compilation

arXiv uses TeXLive 2020+. Your paper uses standard packages that are well-supported:

- `article` document class
- Standard LaTeX packages
- `biblatex` with biber backend
- IEEE citation style

**Note:** arXiv will automatically run:
1. `pdflatex main.tex`
2. `biber main`
3. `pdflatex main.tex` (twice)

## Common Issues and Solutions

### Issue: "Bibliography not found"
**Solution:** Ensure `references.bib` is included in your submission

### Issue: "Figure not found"
**Solution:** 
- Check figure file names (case-sensitive)
- Ensure figures are in the submission package
- Use relative paths: `figures/image.pdf` not absolute paths

### Issue: "Package not found"
**Solution:** 
- Use only standard LaTeX packages
- arXiv supports most common packages
- Avoid proprietary or uncommon packages

### Issue: "Compilation timeout"
**Solution:**
- Reduce figure sizes/quality
- Remove unnecessary packages
- Simplify complex TikZ diagrams

## Post-Submission

After submission:
1. arXiv moderators review (1-2 business days)
2. Paper is announced daily at 20:00 EST
3. You receive an arXiv identifier (e.g., `arXiv:2401.12345`)
4. Paper becomes publicly available

## Updating Your Paper

To replace/update your submission:
1. Go to arXiv.org and login
2. Navigate to your paper
3. Click "Replace" 
4. Upload new version
5. Explain changes in comments

## License

By default, arXiv uses:
- arXiv.org perpetual, non-exclusive license
- You retain copyright
- Allows arXiv to distribute your work

See: https://arxiv.org/help/license

## Resources

- arXiv Help: https://info.arxiv.org/help/
- Submit Guide: https://info.arxiv.org/help/submit/index.html
- TeX/LaTeX Help: https://info.arxiv.org/help/submit_tex.html
- Format Requirements: https://info.arxiv.org/help/policies/format_requirements.html

