# Agent Instructions

These instructions apply to all automated or assisted work in this repository.

## Required reading

Before inspecting, editing, testing, reviewing, committing, pushing, or opening
PRs for this repository, read `CONTRIBUTING.md` in full.

For pull request work, also read:

- `.github/PULL_REQUEST_TEMPLATE.md`
- `docs/contributing/pr-dependency-checks.md`
- `docs/contributing/review-guide.md`
- `docs/contributing/testing.md`

For issue-facing work, also read the relevant issue template under
`.github/ISSUE_TEMPLATE/` before drafting, opening, claiming, or updating an
issue.

## Pull request discipline

Every PR must follow `.github/PULL_REQUEST_TEMPLATE.md`.

Use `docs/contributing/pr-dependency-checks.md` before marking work complete.
When a change affects behavior, output, docs, packaging, CI, examples, schemas,
golden files, release notes, or repository manifests, update every dependent artifact
in the same PR.

Keep PRs narrow. Prefer one layer per PR unless a mechanical change is proven by
tests. Do not mark a PR ready for review while required checks are pending or
failing.

## Issue discipline

Use the repository issue templates as the public contract for issue content.
Before starting issue work, check for duplicates, current `main` behavior, the
newest published release when relevant, labels, assignees, linked PRs, and the
security reporting path in `SECURITY.md`.

## Validation

Run the narrowest meaningful local checks for the changed surface. For docs and
template changes, include `python -m mkdocs build --strict` and the relevant
template or manifest tests. For code changes, prefer the repository CI commands
listed in `CONTRIBUTING.md` and `.github/PULL_REQUEST_TEMPLATE.md`.
