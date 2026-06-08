# SciEqLint

SciEqLint catches exact scalar algebra mistakes and broken equation references in a
documented subset of scientific documents.

Run it on Markdown/MyST docs before review to catch mistakes like this:

```tex
(a+b)^2 = a^2 + b^2
```

Diagnostic:

```text
ALG001 algebraic identity does not hold
left - right = 2*a*b
```

It also catches supported broken equation references:

```md
See {eq}`missing`.
```

Diagnostic:

```text
REF002 equation reference target not found: missing
```

## Install for local development

```bash
python -m pip install -e '.[dev]'
scieqlint --help
scieqlint check .
scieqlint check README.md
scieqlint check examples/bad/famous_bad.md --format github
scieqlint demo
```

## Commands

```bash
scieqlint check [PATH_OR_GLOB...]
scieqlint init
scieqlint demo
scieqlint explain CODE
python -m scieqlint --help
```

## Project promise

SciEqLint is deterministic. Given the same files, config, and version, it must emit
the same diagnostics in the same order. Supported math is checked exactly.
Unsupported math is reported as unknown or skipped. The checker must not guess.

## Supported files

SciEqLint checks `.md`, `.markdown`, `.tex`, and `.ipynb` documents. It supports
Markdown/MyST display math, supported LaTeX containers, notebook Markdown cells,
labels and references, simple scalar algebra, text output, deterministic JSON output,
and JSON Schema validation. See `docs/limitations.md` for the supported subset.

## Pull request annotations

```yaml
- name: Check equations
  run: scieqlint check "docs/**/*.md" --format github
```

## Code scanning

```yaml
permissions:
  contents: read
  security-events: write

steps:
  - uses: actions/checkout@v6
  - uses: Kuhai9801/scieqlint@v0.1.5
    with:
      args: check "docs/**/*.md" --format sarif --output scieqlint.sarif
  - uses: github/codeql-action/upload-sarif@v4
    with:
      sarif_file: scieqlint.sarif
      category: scieqlint-docs
```

## For contributors

Start with these files:

- `SPEC.md` for the product and engineering contract.
- `CONTRIBUTING.md` for the local workflow.
- `GOOD_FIRST_ISSUES.md` for scoped starter tasks.
- `ROADMAP.md` for release order and cut rules.
- `docs/contributing/` for deeper guidance.

Keep PRs small and test the behavior they change.

## License

MIT. See `LICENSE`.
