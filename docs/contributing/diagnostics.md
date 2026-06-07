# Contributing diagnostics

Diagnostic codes are user-facing API.

A new diagnostic requires:

- code in `src/scieqlint/diag/catalog.py`,
- tests,
- docs in `docs/diagnostics.md`,
- schema/golden update if output changes,
- changelog entry if user-visible.

Messages should be one sentence without a trailing period. Details may include computed facts. Hints should contain one actionable fix.
