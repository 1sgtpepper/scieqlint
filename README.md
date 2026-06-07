# SciEqLint

SciEqLint catches exact scalar algebra mistakes and broken equation references in a documented subset of scientific documents.

The first public win is deliberately small: run it on Markdown/MyST docs before review and catch mistakes like this:

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

## Status

This repository contains the v11.1 engineering spec, docs, schemas, examples, tests, and a working v0.1.0 implementation for the first narrow use case: Markdown/MyST display math and equation references.

## Install for local development

```bash
python -m pip install -e '.[dev]'
scieqlint --help
scieqlint check README.md
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

SciEqLint is deterministic. Given the same files, config, and version, it must emit the same diagnostics in the same order. Supported math is checked exactly. Unsupported math is reported as unknown or skipped. The checker must not guess.

## What ships first

v0.1.0 only targets `.md` and `.markdown` documents. It supports a narrow Markdown/MyST display-math subset, labels and references, minimal scalar algebra, text output, deterministic JSON output, and JSON Schema validation.

Not in v0.1.0: dimensions, LaTeX files, notebooks, SARIF, GitHub annotations, graph export, symbols, macro expansion, broad CAS behavior, or theorem proving.

## For contributors

Start with these files:

- `SPEC.md` for the product and engineering contract.
- `CONTRIBUTING.md` for the local workflow.
- `GOOD_FIRST_ISSUES.md` for scoped starter tasks.
- `ROADMAP.md` for release order and cut rules.
- `docs/contributing/` for deeper guidance.

Small, boring, exact PRs are the goal. A narrow PR with tests and docs is better than a broad PR that looks impressive but changes multiple layers at once.

## License

MIT. See `LICENSE`.
