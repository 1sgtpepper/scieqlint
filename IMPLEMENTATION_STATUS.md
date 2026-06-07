# Implementation Status

This repository contains the complete specification and the first working analyzer slice.

The included Python package is a v0.1.0 implementation for a narrow Markdown/MyST subset. It can:

- install as a Python package,
- expose `scieqlint` and `python -m scieqlint`,
- provide `check`, `init`, `demo`, and `explain`,
- load built-in config defaults,
- render text and JSON output,
- scan Markdown display math, fenced math, and MyST math directives,
- check simple scalar polynomial identities,
- report duplicate equation labels and missing supported references,
- provide package resources, docs, schemas, examples, and CI templates.

It does not claim broad algebra, dimensions, LaTeX files, notebooks, SARIF, graph export, macro expansion, theorem proving, or Sphinx/Jupyter Book build validation.

The source of truth for feature readiness is `SPEC.md`, the release checklists under `docs/releases/`, golden fixtures, and the changelog.
