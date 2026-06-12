# SciEqLint

[![PyPI](https://img.shields.io/pypi/v/scieqlint.svg)](https://pypi.org/project/scieqlint/)
[![Python versions](https://img.shields.io/pypi/pyversions/scieqlint.svg)](https://pypi.org/project/scieqlint/)
[![CI](https://github.com/Kuhai9801/scieqlint/actions/workflows/ci.yml/badge.svg)](https://github.com/Kuhai9801/scieqlint/actions/workflows/ci.yml)
[![Codecov](https://codecov.io/github/Kuhai9801/scieqlint/graph/badge.svg)](https://app.codecov.io/github/Kuhai9801/scieqlint)
[![Docs](https://github.com/Kuhai9801/scieqlint/actions/workflows/docs.yml/badge.svg)](https://github.com/Kuhai9801/scieqlint/actions/workflows/docs.yml)
[![CodeQL](https://github.com/Kuhai9801/scieqlint/actions/workflows/codeql.yml/badge.svg)](https://github.com/Kuhai9801/scieqlint/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Kuhai9801/scieqlint/badge)](https://scorecard.dev/viewer/?uri=github.com/Kuhai9801/scieqlint)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

SciEqLint lints scientific Markdown, LaTeX, and notebooks for equation mistakes,
broken references, and CI-ready diagnostics before they reach reviewers.

![SciEqLint demo](docs/assets/scieqlint-readme-demo.gif)

```bash
python -m pip install scieqlint
scieqlint check README.md
```

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

## Install

```bash
python -m pip install scieqlint
scieqlint check .
```

For local development:

```bash
python -m pip install -e '.[dev]'
scieqlint --help
scieqlint check .
scieqlint check examples/bad/famous_bad.md --format github
scieqlint demo
```

## Commands

```bash
scieqlint check [PATH_OR_GLOB...]
scieqlint graph [PATH_OR_GLOB...] --output scieqlint-graph.json
scieqlint init
scieqlint init --preset mechanics
scieqlint presets list
scieqlint presets show mechanics
scieqlint demo
scieqlint explain CODE
python -m scieqlint --help
```

## Deterministic output

SciEqLint is deterministic. Given the same files, config, and version, it must emit
the same diagnostics in the same order. Supported math is checked exactly.
Unsupported math is reported as unknown or skipped. The checker must not guess.

## Supported files

SciEqLint checks `.md`, `.markdown`, `.tex`, and `.ipynb` documents. It supports
Markdown/MyST display math, supported LaTeX containers, notebook Markdown cells,
labels and references, simple scalar algebra, text output, deterministic JSON output,
SARIF, and JSON Schema validation. See `docs/limitations.md` for the exact
scanner and grammar coverage.

Current release target: v1.0.0.

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
  - uses: Kuhai9801/scieqlint@v1.0.0
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
