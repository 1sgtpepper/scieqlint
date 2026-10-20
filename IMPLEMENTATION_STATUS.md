# Implementation Status

v1.2.2 is the final planned release of the current Beta static linter. Its
[release criteria](RELEASE_CHECKLIST.md#v122-product-criteria) cover the supported
scope below. The unfinished R1 host/session migration is not scheduled.

The analyzer can:

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
- preserve source-neutral cross-reference metadata facts and the `REF007` conflict
  contract, including built-in recorded notebook-output boundaries,
- apply suppressions and diagnostic baselines,
- export a deterministic equation label/reference graph,
- provide packaged schemas and presets alongside repository examples, docs, and CI templates.

It does not claim broad algebra, macro expansion, code-cell execution, theorem
proving, or Sphinx/Jupyter Book build validation. Generated-output anchor auditing
is available to callers that provide source-to-generated provenance facts.

Feature readiness is recorded in `SPEC.md`, the current product criteria in
`RELEASE_CHECKLIST.md`, the earlier release checklists under `docs/releases/`,
golden fixtures, and the changelog.
