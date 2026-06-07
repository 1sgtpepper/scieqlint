# Release Checklist

Every release must include:

- release scope statement,
- acceptance checklist status,
- changelog entry,
- version bump,
- docs update,
- diagnostic catalog update when needed,
- JSON/SARIF schema update when needed,
- accuracy benchmark update when expectations change,
- golden test update when output changes,
- wheel install smoke test,
- package-data verification,
- release notes with migration notes,
- explicit note that deferred features remain out of scope.

## Release sequence

1. Scope lock: update acceptance checklist.
2. Data contracts: update models, diagnostics, and schemas first.
3. Core implementation: scanner/parser/checker/reporter changes in separate PRs.
4. Golden fixtures: add good/bad examples and exact output expectations.
5. Docs: update quickstart, limitations, diagnostics, and integration pages.
6. Package smoke: build wheel, install in a clean venv, run CLI smoke.
7. Release candidate: tag rc or create pre-release branch.
8. Final tag: publish only after acceptance criteria pass.

A feature is not shipped until docs and fixtures demonstrate it.
