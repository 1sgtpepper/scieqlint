# Release Checklist

Every release must include:

- release scope statement,
- release check status,
- changelog entry,
- version bump,
- docs update,
- diagnostic catalog update when needed,
- JSON/SARIF schema update when needed,
- accuracy benchmark update when expectations change,
- golden test update when output changes,
- wheel install smoke test,
- package-data verification,
- source, wheel, and stable-tag version identity,
- at least 100 independently labeled semantic equations executed through the public
  analysis path with their expected diagnostics and exit status,
- the 100-document/500-equation/500-reference representative workload completing within three seconds,
- release notes with migration notes.

The checked-in accuracy corpus currently contains 2 independently labeled semantic
equations (one positive and one negative), so stable publication remains blocked at
2/100 until 100 independently labeled semantic equations are available.

## Release sequence

1. Scope lock: update release checks.
2. Data contracts: update models, diagnostics, and schemas first.
3. Core implementation: scanner/parser/checker/reporter changes in separate PRs.
4. Golden fixtures: add good/bad examples and exact output expectations.
5. Docs: update quickstart, limitations, diagnostics, and integration pages.
6. Package smoke: build wheel, install in a clean venv, run CLI smoke.
7. Release candidate: tag rc or create pre-release branch.
8. Trusted publishing: configure the PyPI publisher for `.github/workflows/release.yml`
   and environment `pypi`.
9. Final tag: publish only after release checks pass.

A feature is not shipped until docs and fixtures demonstrate it.
