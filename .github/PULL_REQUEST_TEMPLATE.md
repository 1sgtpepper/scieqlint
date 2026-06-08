## Summary

<!-- What changed, in one or two sentences? -->

## Linked issue

<!-- Example: Fixes #123, Part of #123, or docs-only. -->

## PR Checklist

- [ ] Linked issue checked.
- [ ] One layer or one mechanical change.
- [ ] Behavior/schema/golden impact checked.
- [ ] Tests/docs updated.
- [ ] Local checks run.
- [ ] Keep draft until required CI is green.

## Release target

<!-- Example: v0.0.1, v0.1.0, docs-only, unreleased governance. -->

## Single layer changed

Choose one unless this is a mechanical change proven by tests:

- [ ] scanner
- [ ] parser
- [ ] checker
- [ ] reporter/schema
- [ ] config
- [ ] docs/governance
- [ ] packaging/CI

## Behavior impact

- [ ] No user-visible behavior change
- [ ] User-visible behavior change
- [ ] Diagnostic behavior change
- [ ] JSON/SARIF/schema change
- [ ] Golden output change

## Tests and docs

- [ ] Tests added/updated
- [ ] Golden files added/updated
- [ ] Docs updated
- [ ] Limitations updated
- [ ] Changelog updated

## Dependency checklist

Use `docs/contributing/pr-dependency-checks.md` to decide which dependent
artifacts must be updated. Mark each row that applies, or `N/A` with a short
reason.

| Change area | Dependent artifacts checked |
|---|---|
| CLI/API/config | N/A or list: help text, docs/configuration.md, docs/api.md, README quickstart, tests |
| Scanner/parser/checker behavior | N/A or list: fixtures, accuracy benchmarks, limitations, diagnostics, tests |
| Diagnostics/severity | N/A or list: catalog, docs/diagnostics.md, schemas/reporters/goldens, changelog |
| Reporter/schema/output | N/A or list: schemas, golden files, integration docs, examples, package data |
| Packaging/CI/integrations | N/A or list: action/pre-commit metadata, workflows, release docs/checklists, PACK_MANIFEST.md |
| Docs/governance only | N/A or list: linked pages, mkdocs nav, PACK_MANIFEST.md, stale examples, no behavior claims |

## Local checks

Paste relevant commands and results:

```bash
pytest
ruff format --check .
ruff check .
pyright
```
