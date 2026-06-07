# Good First Issues

These are seed issues for opening the repository. Each one is intentionally small, reviewable, and scoped to one layer.

## 1. CLI smoke tests for v0.0.1

Release: v0.0.1. Area: CLI. Scope: required.

Why it matters: every contributor needs a reliable command surface before real checks exist.

Likely files: `src/scieqlint/cli.py`, `tests/test_cli.py`.

Acceptance:

- `scieqlint --help` exits 0.
- `scieqlint demo` exits 0.
- `python -m scieqlint --help` exits 0.
- Tests use `click.testing.CliRunner`.

Non-goals: real scanning, parser work, JSON schema changes.

## 2. LineIndex tests

Release: v0.1.0. Area: IO. Scope: required.

Why it matters: stable source locations are the foundation for local output, JSON, GitHub annotations, and SARIF.

Likely files: `src/scieqlint/io/source.py`, `tests/test_source.py`.

Acceptance:

- offsets map to one-based line and column,
- mixed short lines are covered,
- final-line/no-final-newline cases are covered,
- implementation is deterministic.

Non-goals: scanner extraction and notebook cell mapping.

## 3. Diagnostic catalog table

Release: v0.1.0. Area: diagnostics/docs. Scope: required.

Why it matters: diagnostic codes are user-facing API.

Likely files: `src/scieqlint/diag/catalog.py`, `docs/diagnostics.md`, `tests/test_diagnostic_catalog.py`.

Acceptance:

- all v0.1.0 codes exist,
- each code has severity, message, explanation, and release,
- docs list every code,
- tests fail if docs/catalog drift.

Non-goals: adding new diagnostics.

## 4. Markdown display math fixture extraction

Release: v0.1.0. Area: scanner. Scope: required.

Why it matters: the first product wedge depends on reliable Markdown display math extraction.

Likely files: `src/scieqlint/scan/markdown.py`, `tests/test_markdown_scan.py`, `tests/fixtures/good/algebra_good.md`.

Acceptance:

- `$$ ... $$` blocks are extracted,
- line/column spans are stable,
- scanner does not parse expressions,
- unterminated containers warn instead of crashing.

Non-goals: MyST directives, inline math, algebra.

## 5. MyST directive label extraction

Release: v0.1.0. Area: scanner. Scope: required.

Why it matters: MyST/Jupyter Book users get zero-config reference checks.

Likely files: `src/scieqlint/scan/markdown.py`, `tests/test_myst_scan.py`, `tests/fixtures/good/myst_good.md`.

Acceptance:

- `````{math}` with `:label:` extracts a label,
- `{eq}` and simple `{numref}` roles extract references,
- raw reference text is preserved,
- source spans are deterministic.

Non-goals: full Sphinx/MyST build behavior.

## 6. Parser unsupported-function regression tests

Release: v0.1.0. Area: parser. Scope: required.

Why it matters: unsupported math must be reported as unknown, not guessed.

Likely files: `src/scieqlint/parse/parser.py`, `tests/test_parser.py`.

Acceptance:

- `\sin(x)`, `\cos(x)`, `\log(x)`, and `\exp(x)` emit `PARSE021`,
- no exception is raised,
- no algebra diagnostic is emitted for unsupported functions.

Non-goals: supporting trig/log/exp.

## 7. Algebra famous-bad fixture

Release: v0.1.0. Area: checker. Scope: required.

Why it matters: the README demo must be real and locked.

Likely files: `src/scieqlint/check/algebra.py`, `tests/fixtures/bad/famous_bad.md`, `tests/golden/text/famous_bad.txt`.

Acceptance:

- `(a+b)^2 = a^2 + b^2` emits `ALG001`,
- detail includes `left - right = 2*a*b`,
- output is stable across operating systems.

Non-goals: broad simplification, trig identities, dimensions.

## 8. JSON schema validation test

Release: v0.1.0. Area: reporter/schema. Scope: required.

Why it matters: JSON is the first automation contract.

Likely files: `src/scieqlint/report/json.py`, `src/scieqlint/schemas/*.json`, `tests/test_json_schema.py`.

Acceptance:

- golden JSON validates against checked-in schema,
- all nullable keys are present,
- no timestamps are emitted,
- paths are relative by default.

Non-goals: SARIF, GitHub annotations.

## 9. Limitations page first pass

Release: v0.1.0. Area: docs. Scope: required.

Why it matters: limitations are a trust asset.

Likely files: `docs/limitations.md`.

Acceptance:

- supported grammar table exists,
- supported label/reference forms are listed,
- unsupported examples are shown,
- “unknown” is explained,
- docs do not imply broad math verification.

Non-goals: marketing copy.

## 10. Package-resource smoke test

Release: v0.0.1/v0.1.0. Area: packaging. Scope: required.

Why it matters: installed wheels must include grammar, schemas, examples, and `py.typed`.

Likely files: `pyproject.toml`, `src/scieqlint/io/resources.py`, `tests/test_package_resources.py`.

Acceptance:

- package resources load through `importlib.resources`,
- wheel build includes schemas and grammar,
- clean install smoke test can run `scieqlint --help`.

Non-goals: parser implementation.
