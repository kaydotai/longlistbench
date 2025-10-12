# lost-and-found-entities

## Development Setup

### Installing the Pre-Commit Hook

To ensure the paper compiles successfully before committing, install the pre-commit hook:

```bash
# From the repository root
cp pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

The hook will automatically run `make` in the `paper` directory before each commit and prevent the commit if compilation fails.

**Manually invoking the hook:**
```bash
# Test the hook without committing
.git/hooks/pre-commit
```

**Note:** You can skip the hook for a specific commit using:
```bash
git commit --no-verify
```

### Requirements

- LaTeX distribution (TeX Live, MacTeX, or similar)
- `pdflatex` and `biber` must be available in your PATH