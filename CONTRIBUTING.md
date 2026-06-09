# Contributing to SciEqLint

SciEqLint changes are scoped by release, layer, and test surface.

## Start here

1. Read `README.md` for the project summary.
2. Read the first sections of `SPEC.md`: product contract, release ladder, v0.1.0 scope, data contracts, parser/algebra boundaries, reporters, testing, and release checklist.
3. Pick an issue from `GOOD_FIRST_ISSUES.md` or a GitHub issue labeled `good first issue`, `good second issue`, or `help wanted`.
4. Run the local quality loop before opening a PR.

## Local setup

```bash
git clone https://github.com/<owner>/scieqlint.git
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

- the release target,
- the single layer it changes,
- whether user-visible behavior changes,
- whether golden output changes,
- whether docs were updated,
- which dependent artifacts from `docs/contributing/pr-dependency-checks.md`
  were checked and updated.

One PR should not combine scanner, parser, checker, reporter/schema, config, docs, and CI changes unless the change is mechanical and tests prove the coupling.

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
4. Record the exact SciEqLint version or commit, Python version, operating system, command, input, and output.
5. Keep the reproduction small enough for another contributor to run directly.
6. State actual behavior and expected behavior separately.
7. Link source references, docs pages, fixtures, or diagnostics when they are already known.
8. Keep feature and task issues narrow enough to review in one pass.

Do not open a public issue for a security vulnerability. Use `SECURITY.md`.

If a bug no longer reproduces on `main`, say that in the issue and include the
older version where it was observed. If it reproduces on `main` but not the
newest release, mark it as unreleased behavior.

Use this quick checklist before submitting:

- [ ] Duplicate search done.
- [ ] Security path checked.
- [ ] Current `main` checked for bugs.
- [ ] Newest release checked for bugs.
- [ ] Exact version, command, input, and output included.
- [ ] Actual and expected behavior are separate.
- [ ] Source references included.
- [ ] Issue is narrow enough for one focused PR.

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
