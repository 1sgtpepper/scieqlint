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

- MyST inline-math facts now retain their delimiter kind, source span, surrounding
  text role, and parse status, and `QueryHost.math.inline_math()` exposes the
  candidates and classified facts to downstream engines.
- Generated-document validation now reports high-confidence suspicious formula
  text as source-spanned `GEN002` diagnostics when the `generated-myst` profile is
  selected, including through the packaged preset.
- Generated-document validation now reports `GEN003` for standalone bracketed
  LaTeX display blocks (`\[...\]` and the literal `[...]` artifact), including
  complete and incomplete forms at source or Markdown-container boundaries;
  diagnostic metadata preserves whether the delimiter was escaped or literal.
- Generated-document validation now reports `GEN004` for standalone
  formula-not-decoded markers, empty dollar or fenced displays, accepted complete
  raw displays, and explicit formula image placeholders.
- Generated-document validation now reports `GEN005` only for isolated text
  items that MathHost classifies as text-leaked math, leaving numeric prose such as
  `1 < 2` quiet.
- Equation reference validation now reports `REF011` when a reference resolves to
  more than one equation target.
- Markdown validation now extracts equation facts from recognized complete raw
  LaTeX environments, including `flalign`; complete unsupported candidates
  preserve parseable facts while remaining unknown math.
- Cross-format reference profiles now materialize equation labels and references
  from Markdown, LaTeX, and notebook source documents.
- The opt-in `math-accessibility` profile now reports `PORT002` for inline math
  facts without configured accessible text.
- The opt-in `typst-portability` profile now reports source-spanned `PORT003`
  risks for focused display-syntax checks in Markdown and LaTeX inputs. Duplicate
  source paths are rejected, and notebook Markdown cells remain outside the profile
  until cell-local source mapping is preserved.

### Changed

- The generated-document workflow now uses the packaged `generated-myst` preset
  on the CLI path. Provenance-backed checks remain an explicit `[profile]` policy
  for already-loaded documents with caller-supplied `SourceOrigin` metadata.
- Generated diagnostic metadata now crosses a post-policy, versioned SchemaHost
  projection seam, so engine and suppression diagnostics reach text, JSON,
  SARIF, and GitHub reporters through one provenance and profile projection
  instead of being reconstructed independently. JSON output
  retains schema 0.1 when no projection metadata is emitted and uses the new 0.2
  schemas when metadata is present. The complete AnalysisResult registry and
  serializer migration remain tracked by #190/#191.
- Programmatic provenance identifiers, source kinds, and conversion stages are
  normalized at construction and reject blank values consistently with TOML input.
- The security policy now documents support for the latest minor in the current
  major release line and provides the private vulnerability-reporting route plus
  a fallback security contact.

### Fixed

- `GEN004` now respects Markdown ownership boundaries, including headings, list
  continuations, completed blocks, opaque HTML, nested source-owned comments, and
  MyST directive options or TeX comments when deciding whether a formula placeholder
  is present.
- Markdown next-line suppressions now cover accepted raw LaTeX displays as one
  source-owned math container, including diagnostics reported on later body lines.
- Reference diagnostics now use one canonical, deterministic path across Markdown,
  LaTeX, and notebook inputs, preserving Markdown-link `REF002` reports without
  duplicate legacy diagnostics and retaining notebook cell identity.
- Accessibility metadata now rejects identifiers that resolve to multiple inline-math
  facts, and `PORT002` remains marked `Unreleased` until its release line is established.
- Accessibility metadata now rejects malformed key/value mappings at the loaded-document
  API boundary, and `PORT002` carries the stable source-owned accessibility ID used by
  those mappings. The `math-accessibility` profile is explicitly limited to Markdown;
  notebook Markdown cells and LaTeX documents remain out of scope.
- Generated formula-text checks now exclude math directive options while retaining
  the exact source locations of artifacts in the formula body.
- TeX equation labels and references in math directive options no longer create
  targets or missing-reference diagnostics; explicit MyST label options remain active.
- Backtick quotes inside raw TeX environments no longer hide their closing
  delimiters or later equation targets. Markdown code opened first stays opaque.
- Plain-text inline-math candidates now scan relation-free input linearly, preserve
  signed decimal operands, reject unsupported attached groups and malformed
  continuations without publishing a truncated prefix, classify arithmetic
  symmetrically around relations, and inherit list or blockquote continuation roles
  from shared Markdown ownership.
- Opaque inline syntax now terminates an unclosed `\(` candidate without hiding a later
  disjoint `\(...\)` span.
- LaTeX-parenthesis math no longer pairs across source lines or closes inside an active
  TeX comment, and explicit math inside link text is delimiter-independent while link
  metadata and inferred label text stay opaque.
- Inline-math candidates now honor the frontend's complete link-aware ownership
  snapshot and are rejected when any part crosses syntax owned by another construct.
- Nested active `\(` or `\)` delimiters in a `\(...\)` candidate are now
  classified as ambiguous unsupported math instead of a preserved formula.
- Profile model construction and TOML loading now reject unknown or non-string profile choices
  with deterministic `ValueError` results.
- Cross-format profile inputs now reject duplicate document paths before fact lowering so
  reference identities and diagnostics remain deterministic.
- Architecture terminology scans now recognize longer matching fenced-code closers
  instead of treating the remaining document as fence content.
- Stable-tag publication now fails closed unless source, wheel, and tag versions
  agree, at least 100 documented equation fixtures execute successfully, and the
  100-document/500-equation/500-reference workload stays under three seconds.
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
- Raw-LaTeX ownership now suppresses compatibility references from opaque
  Markdown candidates, preserves later equations after opaque inline markers,
  keeps unmatched dollar displays from exposing later raw environments, and
  makes unsupported-environment classification idempotent.
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
