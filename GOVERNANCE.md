# Governance

SciEqLint is governed by the product contract in `SPEC.md`.

## Decision-making

Maintainers should prefer decisions that improve determinism, exactness, user trust, contributor clarity, and release focus.

When tradeoffs conflict, use this priority order:

1. Security and correctness.
2. Deterministic output contracts.
3. Scope discipline.
4. Contributor experience.
5. Feature breadth.

## Spec changes

Changes to `SPEC.md` require:

- a clear motivation,
- release impact,
- migration impact if any,
- updated docs/checklists/templates if affected.

## Diagnostic and schema stability

Diagnostic codes and schema fields are user-facing contracts once introduced. They may be refined during v0.x, but changes require changelog entries, docs updates, tests, and migration notes when applicable.
