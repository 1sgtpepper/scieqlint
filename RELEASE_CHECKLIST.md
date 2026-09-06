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
- package CI source-distribution test-suite and clean wheel install/CLI smoke gates,
- stable release workflow's separate clean wheel and source-distribution install/CLI smoke gates,
- package-data verification,
- source, wheel, source-distribution, and stable-tag version identity,
- release provenance bound to the protected `main` commit and an immutable stable tag,
- exactly one wheel and one source distribution, with no extra distribution files,
- the generated-formula quality corpus and exact text/JSON goldens executed against
  both installed release artifacts,
- at least 100 independently labeled semantic equations executed through the public
  analysis path with their expected diagnostics and exit status,
- the 100-document/500-equation/500-reference representative workload completing within three seconds,
- release notes with migration notes.

## Release sequence

1. Scope lock: update release checks.
2. Data contracts: update models, diagnostics, and schemas first.
3. Core implementation: scanner/parser/checker/reporter changes in separate PRs.
4. Golden fixtures: add good/bad examples and exact output expectations.
5. Docs: update quickstart, limitations, diagnostics, and integration pages.
6. Package CI: build wheel and source distribution, run the source-distribution test suite
   from an extracted tree, and install the wheel in a clean venv for CLI smoke.
7. Release candidate: use a documented prerelease tag such as `v1.1.0rc1` or a prerelease
   branch; the stable release workflow does not consume prerelease tags.
8. Stable tag: after all changes are merged to protected `main`, create an immutable stable
   semver tag at that exact commit. The release workflow rechecks that relationship before
   publication, installs the wheel and source distribution in separate clean venvs, and
   runs CLI and behavioral smoke for each.
9. Trusted publishing: configure the PyPI publisher for `.github/workflows/release.yml`
   and environment `pypi`; require environment approval and disable administrator bypass.
10. Final tag: publish only after release checks pass, the downloaded artifact digest matches,
    the distribution contains exactly one wheel and one source distribution, and no tag or
    protected-branch SHA changed during verification. Release tooling is constrained by
    `.github/release-constraints.txt`, and each run records its resolved dependencies.

A feature is not shipped until docs and fixtures demonstrate it.
