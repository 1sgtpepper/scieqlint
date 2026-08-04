# Implementation Status

This repository contains the v1.1.0 stable analyzer and its complete implementation
status.

The included Python package is a v1.1.0 implementation. It can:

- install as a Python package,
- expose `scieqlint` and `python -m scieqlint`,
- provide `check`, `graph`, `init`, `demo`, `explain`, and preset commands,
- load built-in config defaults,
- render text, JSON, GitHub annotation, and SARIF output,
- scan Markdown/MyST structure, display math, fenced math, and math directives,
- scan supported LaTeX display containers and notebook Markdown cells without
  executing notebooks,
- check simple scalar polynomial identities and configured dimensions,
- report duplicate labels, missing equation and generic references, and undefined
  symbols from explicit directives,
- apply suppressions and diagnostic baselines,
- export a deterministic equation label/reference graph,
- provide package resources, docs, schemas, examples, and CI templates.

It does not claim broad algebra, macro expansion, code-cell execution, theorem
proving, or Sphinx/Jupyter Book build validation. Generated-output anchor auditing
is available to callers that provide source-to-generated provenance facts.

The source of truth for feature readiness is `SPEC.md`, the release checklists under `docs/releases/`, golden fixtures, and the changelog.
