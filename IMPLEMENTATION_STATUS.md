# Implementation Status

This repository contains the complete specification and the v1.0.0 analyzer core.

The included Python package is a v1.0.0 implementation. It can:

- install as a Python package,
- expose `scieqlint` and `python -m scieqlint`,
- provide `check`, `init`, `demo`, and `explain`,
- load built-in config defaults,
- render text, JSON, GitHub annotation, and SARIF output,
- scan Markdown display math, fenced math, and MyST math directives,
- scan supported LaTeX display containers,
- scan notebook Markdown cells without executing notebooks,
- check simple scalar polynomial identities,
- check configured dimensions,
- report duplicate equation labels and missing supported references,
- export equation reference graphs,
- check explicit symbol definitions,
- provide package resources, docs, schemas, examples, and CI templates.

It does not claim broad algebra, macro expansion, code-cell execution, theorem
proving, or Sphinx/Jupyter Book build validation.

The source of truth for feature readiness is `SPEC.md`, the release checklists under `docs/releases/`, golden fixtures, and the changelog.
