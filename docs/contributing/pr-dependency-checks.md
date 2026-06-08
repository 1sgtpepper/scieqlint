# PR dependency checks

Use this guide before opening or marking a PR ready. The goal is to make every
behavior or contract change update the artifacts that depend on it.

## How to use this page

1. Pick the changed layer from the PR template.
2. Check the matching row below.
3. Update every dependent artifact that applies.
4. Keep the PR draft until every dependent artifact is current.

## Dependency map

| Change area | Usually update | Usually verify |
|---|---|---|
| CLI command, option, or exit behavior | `README.md`, `docs/quickstart.md`, `docs/api.md`, `docs/configuration.md`, CLI tests | `python -m scieqlint --help`, `python -m scieqlint check --help`, focused CLI tests |
| Public API or result model | `docs/api.md`, schemas when output shape changes, package-resource tests | API tests, JSON schema tests, type checks |
| Config loading or defaults | `docs/configuration.md`, root `scieqlint.toml`, config tests, quickstart examples when defaults affect first use | config tests, CLI smoke with and without `--config` |
| Scanner source support or spans | `docs/limitations.md`, fixtures under `tests/fixtures/`, scanner tests, accuracy benchmarks when expectations change | scanner tests, source-span tests, representative CLI run |
| Parser grammar or unsupported syntax | `docs/limitations.md`, parser tests, unsupported regression tests, accuracy benchmarks | parser tests plus a neighboring unsupported case |
| Algebra, dimension, or reference checks | `docs/diagnostics.md`, `docs/limitations.md`, examples, checker tests, accuracy benchmarks | checker tests, focused CLI or API regression |
| Diagnostic code, severity, or message | `src/scieqlint/diag/catalog.py`, `docs/diagnostics.md`, reporter/golden tests, changelog when user-visible | catalog tests, reporter tests, golden output checks |
| Text, JSON, GitHub, or SARIF output | reporter implementation, `tests/golden/`, schemas, integration docs, examples | golden tests, schema validation, integration-specific tests |
| JSON/SARIF schema contract | `schemas/`, packaged schema copies under `src/scieqlint/schemas/`, docs, package-resource tests | schema tests, package-resource tests, golden validation |
| GitHub Action or pre-commit integration | `action.yml`, `.pre-commit-hooks.yaml`, integration docs, release checklist when versioned | metadata tests, workflow/example tests |
| Packaging, release, or CI | `pyproject.toml`, workflows, `RELEASE_CHECKLIST.md`, `PACK_MANIFEST.md`, release docs, changelog when release-facing | package tests, workflow metadata tests, manifest check, relevant CI job locally or in Actions |
| Docs or governance only | linked docs pages, `mkdocs.yml`, `PACK_MANIFEST.md`, examples in README/docs, stale release/version references | `python -m mkdocs build --strict`, manifest check, relevant docs contract tests |

## Changelog rule

Update `CHANGELOG.md` when a change is user-visible, release-facing, or changes a
published contract. For contributor-documentation changes, check the changelog and
record docs-only scope in the PR.

## Negative checks

Some changes need proof that nearby behavior did not change:

- parser changes should keep a neighboring unsupported form unsupported,
- config changes should cover invalid or old-form config where relevant,
- reporter/schema changes should validate old fixtures or intentionally update
  golden output,
- integration changes should keep the documented example aligned with checked
  metadata.
