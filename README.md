# SciEqLint

[![PyPI](https://img.shields.io/pypi/v/scieqlint.svg)](https://pypi.org/project/scieqlint/)
[![Python versions](https://img.shields.io/pypi/pyversions/scieqlint.svg)](https://pypi.org/project/scieqlint/)
[![CI](https://github.com/1sgtpepper/scieqlint/actions/workflows/ci.yml/badge.svg)](https://github.com/1sgtpepper/scieqlint/actions/workflows/ci.yml)
[![Codecov](https://codecov.io/github/1sgtpepper/scieqlint/graph/badge.svg)](https://app.codecov.io/github/1sgtpepper/scieqlint)
[![Docs](https://github.com/1sgtpepper/scieqlint/actions/workflows/docs.yml/badge.svg)](https://github.com/1sgtpepper/scieqlint/actions/workflows/docs.yml)
[![CodeQL](https://github.com/1sgtpepper/scieqlint/actions/workflows/codeql.yml/badge.svg)](https://github.com/1sgtpepper/scieqlint/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/1sgtpepper/scieqlint/badge)](https://scorecard.dev/viewer/?uri=github.com/1sgtpepper/scieqlint)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

SciEqLint lints scientific Markdown, LaTeX, and notebooks for equation mistakes,
broken references, MyST structure problems, and CI-ready diagnostics before they
reach reviewers.

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
  equation: (a+b)^2 = a^2 + b^2
  detail: left - right = 2*a*b
```

It also catches supported broken equation references:

```md
See {eq}`missing`.
```

Diagnostic:

```text
REF002 equation reference target not found: missing
```

For generated or MyST-heavy scientific docs, initialize the packaged profile and
run the same deterministic checks in CI:

```bash
scieqlint init --preset generated-myst --path scieqlint.generated-myst.toml
scieqlint check "docs/**/*.md" --config scieqlint.generated-myst.toml --format github
```

That profile enables stricter generated-document checks while keeping the scope
source-based: math containers, supported equation and generic references, MyST
anchors and directives, heading hierarchy, and parse-unknown diagnostics.

## Local development

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
scieqlint init --preset generated-myst
scieqlint init --preset mechanics
scieqlint presets list
scieqlint presets show generated-myst
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
labels and references, MyST structure diagnostics, simple scalar algebra, text
output, deterministic JSON output, SARIF, and JSON Schema validation. See
`docs/limitations.md` for the exact scanner and grammar coverage.

Current release target: v1.1.0.

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
  - uses: actions/setup-python@v6
    with:
      python-version: "3.11"
  - run: python -m pip install scieqlint==1.1.0
  - run: rm -f scieqlint.sarif
  - run: set +e; scieqlint check "docs/**/*.md" --format sarif --output scieqlint.sarif; status=$?; test "$status" -le 1 || exit "$status"
  - run: test -s scieqlint.sarif && python -m json.tool scieqlint.sarif >/dev/null
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
