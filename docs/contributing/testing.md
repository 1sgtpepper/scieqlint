# Testing

Tests protect documented behavior, not just code coverage.

## Test types

- Unit tests for data contracts and pure logic.
- Scanner tests for extraction and spans.
- Parser tests for supported and unsupported syntax.
- Checker tests for exact behavior.
- Golden tests for text, JSON, GitHub, and SARIF outputs.
- Package-resource tests for installed wheels.
- Pre-commit integration tests build a temporary hook repository from the source
  under test, so they do not depend on the checkout's Git revision.
- Source distributions include the inputs required by the shipped test suite. CI runs
  that suite from an extracted archive; the repository-only pack-manifest inventory
  check is skipped when Git metadata is unavailable.

## Public bug regressions

Keep regressions beside the component that owns the behavior and exercise the public
in-memory analysis path. Assert the complete ordered diagnostic semantics, relevant
result counts, and source spans derived independently from the input. A clean regression
must include a nearby active control that would fail if the scanner, parser, or checker
were disabled. Use pytest node or parameter IDs as the runnable case identity.

Mark only a newly added test that reproduces a public bug with
`@pytest.mark.public_regression`. Do not mark active controls, normative contract tests,
or existing tests being strengthened. Pull-request CI runs each new marked node against
the head and base package sources. The node is accepted only when head passes and base
fails by an assertion that pytest attributes to the proposed `tests/` tree. Direct test
assertions, private test helpers, and `pytest.fail()` are valid oracles; an assertion from
the package or a dependency is an API incompatibility unless the test catches it and
asserts the intended behavior explicitly. Setup and teardown must both pass normally:
failures, skips, and expected-failure outcomes in either phase are incompatible. A base
pass or API incompatibility is rejected and reported with the exact node ID.

To replay against an existing base checkout directly:

```bash
python tools/public_regression_replay.py --base ../scieqlint-base
```

## Local loop

```bash
pytest
pytest --cov=scieqlint --cov-report=term-missing
ruff format --check .
ruff check .
pyright
```

A diagnostic behavior change without tests and docs is not complete.
