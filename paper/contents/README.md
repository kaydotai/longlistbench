# Contents Directory

This directory contains all the content sections of your research paper.

## Files

- **`abstract.tex`** - Abstract section
- **`introduction.tex`** - Introduction section with subsections
- **`conclusion.tex`** - Conclusion section with summary and future work
- **`acknowledgments.tex`** - Acknowledgments section

## Usage

These files are automatically included in `main.tex` using the `\input{}` command:

```latex
\begin{abstract}
\input{contents/abstract}
\end{abstract}

\section{Introduction}
\input{contents/introduction}

\section{Conclusion}
\input{contents/conclusion}

\section*{Acknowledgments}
\input{contents/acknowledgments}
```

## Adding New Sections

To add a new section:

1. Create a new `.tex` file in this directory (e.g., `methodology.tex`)
2. Add the section content without `\section{}` heading
3. In `main.tex`, add:
   ```latex
   \section{Methodology}
   \label{sec:methodology}
   \input{contents/methodology}
   ```

## Tips

- **Don't include section headings** in these files - they're added in `main.tex`
- **Use relative references** when citing within sections
- **Keep each section modular** - it makes editing easier
- All files will be submitted together to arXiv in the `contents/` folder

