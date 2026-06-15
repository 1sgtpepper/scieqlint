# Changelog

All notable changes to SciEqLint should be documented here.

Release notes must use these sections:

- Added
- Changed
- Fixed
- Deprecated
- Removed
- Migration notes
- Known limitations

## Unreleased

### Added

- Nothing yet.

### Changed

- Nothing yet.

### Fixed

- Nothing yet.

### Deprecated

- Nothing yet.

### Removed

- Nothing yet.

### Migration notes

- Nothing yet.

### Known limitations

- Nothing yet.

## v1.1.0 - 2026-06-15

### Added

- MyST structure diagnostics for heading syntax, non-math fenced blocks,
  heading hierarchy, directive openers and options, role syntax, and code-cell
  metadata.
- Generic MyST reference diagnostics for missing and ambiguous `{ref}` targets,
  with support for heading anchors such as `(label)=`.
- Generated-output anchor audit support for callers that provide
  source-to-generated provenance facts.
- Packaged `generated-myst` preset for generated Markdown/MyST scientific-doc
  validation with inline math, strict parser unknowns, algebra, references, and
  GitHub annotation workflow documentation.

### Changed

- README, configuration, diagnostics, and GitHub annotation documentation now
  describe generated/MyST scientific-doc validation.

### Fixed

- The SARIF upload example workflow now installs the release package version
  used by the release branch.

### Deprecated

- Nothing yet.

### Removed

- Nothing yet.

### Migration notes

- Nothing yet.

### Known limitations

- Nothing yet.

## v1.0.0 - 2026-06-09

### Added

- Markdown and LaTeX suppression comments for known diagnostic codes, with
  `SUP001` warnings for unknown suppression codes.
- Configured JSON output can include suppressed diagnostics with suppression
  state and reason.
- Packaged `mechanics` preset resource loading for config defaults.
- CLI preset commands for listing, showing, and initializing packaged presets.
- Explicit `[aliases]` config normalization for dimension symbol lookup.
- Graph export data model for equation label nodes and supported reference edges.
- `scieqlint graph` JSON output with schema validation and golden output coverage.
- Explicit Markdown and LaTeX `scieqlint-symbol` directive parsing for later
  symbol-table checks.
- Opt-in undefined-symbol diagnostics from explicit symbol directives.
- Project file ordering for deterministic cross-file checks.
- Diagnostic baselines for known findings in repeated CI runs.
- v1.0.0 contract readiness documentation for CLI, JSON, SARIF, config, graph,
  diagnostics, release checks, and public API surfaces.

### Changed

- CI test coverage now runs across the declared Python 3.11, 3.12, and 3.13
  compatibility matrix.

### Fixed

- Nothing yet.

### Deprecated

- Nothing yet.

### Removed

- Nothing yet.

### Migration notes

- The stable contract freezes the documented CLI, JSON, SARIF, graph JSON,
  configuration, diagnostic, and public API surfaces for v1-compatible users.

### Known limitations

- SciEqLint remains intentionally source-only: it does not execute notebooks,
  import user project modules, expand arbitrary LaTeX macros, or evaluate
  document-provided code.

## v0.1.5 - 2026-06-08

### Added

- Complete v11.1 specification and OSS contributor scaffold.
- v0.1.0 Markdown/MyST analyzer for simple scalar algebra and equation references.
- v0.1.1 GitHub annotation output and pre-commit metadata.
- v0.1.2 dimension config surface and configured dimension diagnostics for supported
  equality, addition, subtraction, multiplication, division, and integer-power expressions.
- v0.1.3 LaTeX source scanning for supported display, equation, and align containers,
  plus LaTeX labels/references, locked by accuracy benchmarks.
- v0.1.4 notebook Markdown-cell scanning with code cells ignored, cell metadata
  preserved, and deterministic schema warnings through `INP002` when readable
  notebook cells can still be scanned best-effort; pre-commit metadata now targets
  `.ipynb` alongside Markdown and LaTeX files.
- v0.1.5 SARIF 2.1.0 output with deterministic partial fingerprints, a
  result-count guard, GitHub upload documentation, and a thin composite Action
  wrapper that installs SciEqLint and runs the CLI.
- CI, docs, issue templates, labels, schemas, examples, and release checklists.

### Changed

- Nothing yet.

### Fixed

- Nothing yet.

### Deprecated

- Nothing yet.

### Removed

- Nothing yet.

### Migration notes

- Initial package release target.

### Known limitations

- The analyzer is intentionally small: Markdown/MyST plus supported LaTeX containers,
  simple scalar polynomial algebra, supported equation references, and configured dimension
  checks only.
- v0.1.2 dimensions require explicit `[vars]` config. Presets, aliases, unit databases,
  and dimension CLI override flags are deferred.
- v0.1.3 LaTeX support is limited to supported containers, `\label`, `\ref`, and
  `\eqref`. Macro expansion, full LaTeX parsing, and broad environment support are
  deferred.
- v0.1.4 notebook support never executes notebooks, ignores code cells, and defers
  code-cell analysis and full Jupyter schema validation.
- v0.1.5 SARIF support is reporter and upload integration scope only. It does not
  add CodeQL queries, a separate analyzer, new scanner behavior, or new math
  support.
