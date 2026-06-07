# Contributing to SciEqLint

Thank you for helping make scientific writing tooling more reliable.

SciEqLint has one contributor rule above all others: keep changes narrow. The project earns trust by shipping exact, deterministic behavior in small slices.

## Start here

1. Read `README.md` for the project promise.
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
- what is explicitly out of scope.

One PR should not combine scanner, parser, checker, reporter/schema, config, docs, and CI changes unless the change is mechanical and tests prove the coupling.

## Review norms

Maintainers review in this order:

1. Scope: is the PR narrow and in the right release?
2. Correctness: does it preserve deterministic exact behavior?
3. Tests and docs: are fixtures, golden outputs, schemas, and limitations updated?
4. Style: only after the first three are satisfied.

Reviewers should not widen a contributor's PR. Prefer opening a follow-up issue.

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
