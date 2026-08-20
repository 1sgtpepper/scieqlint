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

- Generated-document validation now reports high-confidence suspicious formula
  text as source-spanned `GEN002` diagnostics when the explicit
  `generated-myst` profile is selected.
- Replace the permissive YAML-like accuracy fixtures with a strict versioned JSON
  corpus of labeled positive and negative cases and expanded rule coverage; synthetic
  wrappers do not count as independent accuracy evidence.
- Add bounded deterministic Hypothesis properties for source-token span integrity, raw
  newline ingress, and Markdown code-cell fence lowering.
- Add the opt-in `code-cell-metadata` profile, exact code-cell label/language
  facts for Markdown and notebooks, code-cell reference targets, and duplicate-label
  and malformed-language diagnostics.
- Warn when local cross-document references resolve differently after lexical
  project-path normalization.
- Model source-neutral cross-reference metadata across document and engine-output
  boundaries, warning when the same target has incompatible kind or display metadata.
- Lower notebook code-cell renderings, cross-reference options, and output-boundary
  facts, with an opt-in warning for incompatible renderings/crossref combinations.
- Keep visible, hidden, and excluded equation-label facts separate and warn when
  non-visible targets affect a rendered equation reference.
- Track cross-reference display text, target type, and rendered-label intent, with an
  opt-in warning for missing or generic labels on resolved non-heading targets.
- Preserve document-scoped inline-math macro declarations and use sites in source
  order without expanding document-provided TeX.

### Changed

- Generated diagnostic metadata now crosses a versioned SchemaHost projection
  seam, so engines carry semantic provenance and text, JSON, SARIF, and GitHub
  reporters share one public provenance and profile projection instead of
  reconstructing it independently. The complete AnalysisResult registry and
  serializer migration remain tracked by #190/#191.
- The packaged `generated-myst` preset now activates generated-output checks
  alongside the existing scientific checks; path-based checks retain configured
  generated-document metadata without inferring source-document identity.
- The security policy now documents support for the latest minor in the current
  major release line and provides the private vulnerability-reporting route plus
  a fallback security contact.

### Fixed

- Generated formula checks now recognize direct spaced formula artifacts and
  multiline bracketed displays with content on the opener, while leaving
  ordinary rendered equation images out of placeholder diagnostics.
- Stable publication now downloads the exact immutable distribution artifact
  approved by smoke, carrying its artifact ID through the release jobs without
  rebuilding or accepting a separately downloaded artifact; both wheel and source
  distribution members are installed and smoke-tested before publication.
- Architecture terminology scans now recognize longer matching fenced-code closers
  instead of treating the remaining document as fence content.
- Stable-tag publication now fails closed unless source, wheel, source distribution,
  and tag versions agree, at least 100 independently labeled semantic equations
  execute successfully, and the 100-document/500-equation/500-reference workload
  stays under three seconds.
- Markdown math fences now follow the shared CommonMark opener and closer rules,
  including tilde markers, longer fences, and up to three spaces of indentation.
- Terminology-gate detection now counts only canonical gate wiring with direct
  failure controls that are statically proven blocking. Explicitly disabled or
  continue-on-error steps and parent jobs are excluded, as are step shell
  overrides and inherited workflow or job run defaults; general GitHub Actions
  validation remains outside this scanner.
- The development Ruff requirement now stays within the formatter version
  supported by the checked-in sources and documentation.
- Package metadata now links to the repository's working documentation path.
- Notebook JSON integer-conversion failures now produce deterministic `INP001`
  diagnostics and do not prevent later inputs from being checked.
- Dimension aliases now match complete surface tokens instead of splitting
  longer configured identifiers.
- Dimension checks now accept rational factors after implicit multiplication.
- Dimension checks now bound numeric components to 512 decimal digits and group
  nesting to 64 levels, reporting over-budget expressions as `DIM020` and
  continuing with later expressions and documents.
- Algebra checks now evaluate line-separated equations independently instead
  of treating a multi-line block as one chained equality.
- SARIF artifact paths are URI-encoded and runs declare their Unicode code-point
  column convention.
- Text diagnostics now include the equation that produced a finding, and the
  DIM002 and REF002 messages match their documented wording.
- Strict missing-label checks no longer require labels on inline math spans.
- Bare required-arity inline TeX commands now remain source-spanned unknown math
  instead of being classified as preserved math.
- Explicit missing inputs and operational/configuration failures now return controlled
  exit status 2; invalid UTF-8 files report `INP001` without stopping later inputs.
- Graph path analysis now shares check path project discovery, ordering, ignore, display
  path, and source-reading behavior; source failures abort graph construction with
  controlled `INP001` context instead of exposing a raw exception.
- Explicit unsupported source files are now rejected instead of being analyzed as
  Markdown; directory and glob discovery continue to ignore unsupported files, and
  already-loaded `DocumentKind.UNKNOWN` documents are rejected by both APIs.
- Markdown suppressions now stay on the adjacent source line; MyST labels and
  roles respect their syntax boundaries, and seven-hash paragraph lines remain
  ordinary text.
- `scieqlint init` now emits only supported configuration keys, and unknown keys in
  fixed-schema configuration tables are rejected instead of being ignored.
- The SARIF upload example now allows finding exits to reach upload and rejects
  missing, empty, or invalid JSON report files before upload.
- Unsupported TeX function names no longer trigger undefined-symbol warnings.
- Notebook Markdown scans now preserve explicit symbol directives and their cell
  locations for symbol checks.
- During ordinary pre-commit runs, the hook now runs one complete project-context
  check per invocation, including clean `--all-files` and explicit `--files` runs.
  Normal commit hooks use pre-commit's tracked-file staging context while still
  seeing untracked supported files; `--all-files` and `--files` observe the
  current worktree. The hook is limited to the pre-commit stage and requires
  pre-commit 3.2.0 or newer. Consumer hook arguments with positional paths are
  rejected rather than narrowing the project scan.
- Pre-commit launches now use Python isolated mode, including inherited Python path
  variables, so consumer-side modules cannot shadow the installed SciEqLint package.
- Source distributions now include the pre-commit hook manifest so integration
  fixtures can run without repository Git metadata.
- Inline Markdown math spans now retain source offsets for the trimmed math body.
- LaTeX symbol diagnostics now retain exact source offsets after comments, indentation,
  blank lines, and alignment markers are removed during math normalization, without
  joining symbols that were separated by removed markers.
- Algebraic parsing now applies exponentiation before unary signs, keeps
  symbolic square roots conservative, does not simplify symbolic root
  operands after cancellation, accepts integer exponents from `-1000` through
  `1000`, and reports out-of-range, oversized, or deeply nested unsupported
  input without leaking interpreter errors.
- MyST targets now attach to valid bare ATX headings, while malformed ATX
  candidates remain diagnostics without participating in heading semantics.
- Disabling the Markdown scanner now also disables Markdown frontend diagnostics
  and cross-document reference/structure analysis.
- Implementation-status documents now identify the current v1.1.0 implementation
  and its shipped capabilities without changing the unresolved maturity
  classification.
- `check` now refuses `--output` paths that alias the source, configuration, or
  baseline files actually consumed during analysis; `graph` applies the same
  guard to its source and configuration inputs. The guard protects both the
  lexical input role and the object identity captured while reading each
  descriptor, keeps output files write-only, pins the output parent before
  exclusive creation where directory-descriptor opens are supported, and leaves
  stdout/API analysis available when output-safety metadata is unavailable.
- Path-based diagnostics, graph spans, and baseline identities now retain
  caller-visible lexical input paths. Default absolute inputs are rendered
  relative to the current working directory, `--absolute-paths` retains explicitly
  absolute spelling, and read-error details omit the operating-system filename.
- Compact rational factors adjacent to implicit products are now parsed
  consistently with explicit division, with zero denominators and oversized
  literals reported as unsupported syntax.
- Source distributions now include the files required by their shipped test suite,
  and CI executes that suite from an extracted archive.
- Dollar math now honors escaped delimiters, block placement, and complete label
  suffixes, ignores empty bodies, and keeps Markdown code spans and fenced-code
  regions within their delimiter and indentation boundaries.
- Markdown code, raw HTML, fence, and dollar regions now resolve in source order,
  so the first valid opener owns later delimiters until its syntax-specific
  terminator or enclosing container boundary.
- Escaped Markdown backticks no longer open code spans, ordinary inline HTML tags
  no longer hide their contents, and dollar display closers follow source-line
  boundaries and complete label suffixes.
- LaTeX scanning now ignores starred and commented verbatim markers, respects
  TeX control-sequence boundaries outside verbatim, and closes live verbatim
  ranges at their first exact matching delimiter; TeX labels inside Markdown
  math use the same control-sequence boundary. Same-line transitions between
  verbatim content and comments now retain their lexical ownership. Overlapping
  escaped dollar candidates no longer hide an adjacent live display block.
- Markdown links and MyST roles now respect escapes, image syntax, and link metadata
  when creating reference facts; active role bodies are not reparsed as links, and
  decoded backslash/entity destinations retain their original source offsets for
  diagnostics. Link labels stop at paragraph and block boundaries. Link metadata is
  also opaque to math and structure lowering, and link facts share one immutable
  lexical snapshot across producers. CommonMark indented code at a block boundary
  is now opaque to reference tokenization, including container-relative list code,
  while paragraph continuation indentation remains prose. Multiline link titles stop
  at Markdown block boundaries, and malformed destinations have bounded nesting work.
  Fenced code and raw HTML inside quote or list containers remain opaque, Setext and
  list interruption boundaries follow paragraph context, partial lazy quote
  continuations retain their container, and failed enclosing labels no longer copy
  every child token through every open frame.
  Heading-target classification accepts valid empty ATX
  headings without accepting missing-space forms.
- Markdown raw HTML now follows all seven CommonMark HTML-block families, keeping
  block contents opaque to math, references, headings, anchors, and graph facts
  while preserving inline content and dedicated comment directives.

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
