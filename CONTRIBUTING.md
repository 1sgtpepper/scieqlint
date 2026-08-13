# Contributing to SciEqLint

SciEqLint changes are scoped by release, layer, and test surface.

## Start here

1. Read `README.md` for the project summary.
2. Read the first sections of `SPEC.md`: product contract, release ladder, v0.1.0 scope, data contracts, parser/algebra boundaries, reporters, testing, and release checklist.
3. Pick an issue from `GOOD_FIRST_ISSUES.md` or a GitHub issue labeled `good first issue`, `good second issue`, or `help wanted`.
4. Run the local quality loop before opening a PR.

## Local setup

```bash
git clone https://github.com/1sgtpepper/scieqlint.git
cd scieqlint
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
ruff format --check .
ruff check .
pyright
```

Using `uv` is encouraged once the repository has a lockfile:

```bash
uv sync --group dev
uv run pytest
uv run ruff format --check .
uv run ruff check .
uv run pyright
```

## Pull request contract

Every PR must state:

- the behavior changed,
- the linked issue or why no issue applies,
- the exact validation performed.

One PR should not combine scanner, parser, checker, reporter/schema, config, docs, and CI changes unless the change is mechanical and tests prove the coupling.

Bug-fix PRs must link an issue with a runnable reproduction or include the
reproduction directly. Feature, task, documentation, and mechanical PRs do not
require one.

Do not mark a PR ready for review until required CI checks pass.

## Good PR shape

A good PR:

- fixes one issue,
- changes one layer,
- includes the smallest useful test,
- updates docs when behavior changes,
- avoids unrelated formatting.

## Issue workflow

Before opening or taking an issue:

1. Search open and closed issues for the same report or task.
2. Reproduce bugs on the current `main` branch.
3. Reproduce bugs on the newest published release.
4. Include a minimal runnable reproduction, actual behavior, expected behavior,
   and the affected version or revision.
5. For feature, task, and documentation issues, state the user need and expected
   observable result; no reproduction is required.
6. Keep the public issue short. Do not add generic scope, phased-delivery,
   file-inventory, or policy-checklist sections.

Do not open a public issue for a security vulnerability. Use `SECURITY.md`.

If a bug no longer reproduces on `main`, say that in the issue and include the
older version where it was observed. If it reproduces on `main` but not the
newest release, mark it as unreleased behavior.

## Review norms

Maintainers review in this order:

1. Scope: is the PR narrow and in the right release?
2. Correctness: does it preserve deterministic exact behavior?
3. Tests and docs: are fixtures, golden outputs, schemas, and limitations updated?
4. Style: only after the first three are satisfied.

Reviewers should not widen a contributor's PR. Prefer opening a follow-up issue.
PRs with failing or pending required CI should stay draft.

## Diagnostics and behavior changes

Any diagnostic behavior change requires:

- a diagnostic catalog update,
- tests,
- docs update,
- changelog entry if user-visible,
- schema/golden update if output changes.

Any grammar expansion requires:

- parser tests,
- algebra or dimension behavior tests where applicable,
- unsupported regression tests,
- limitations update.

## Security-sensitive areas

The checker runtime must not make network calls, execute notebooks, import user project modules, evaluate Python code from documents, run shell commands from the analysis core, or pass user-controlled math text into SymPy text parsers.

Security issues should be reported through the process in `SECURITY.md`, not public issues.
