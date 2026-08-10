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

## Local loop

```bash
pytest
pytest --cov=scieqlint --cov-report=term-missing
ruff format --check .
ruff check .
pyright
```

A diagnostic behavior change without tests and docs is not complete.
