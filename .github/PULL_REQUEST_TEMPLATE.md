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

- [ ] I checked `docs/contributing/pr-dependency-checks.md` and updated every dependent artifact.

## Local checks

Paste relevant commands and results:

```bash
pytest
ruff format --check .
ruff check .
pyright
```
