# Testing

Tests protect documented behavior, not just code coverage.

## Test types

- Unit tests for data contracts and pure logic.
- Scanner tests for extraction and spans.
- Parser tests for supported and unsupported syntax.
- Checker tests for exact behavior.
- Golden tests for text, JSON, GitHub, and SARIF outputs.
- Package-resource tests for installed wheels.

## Local loop

```bash
pytest
pytest --cov=scieqlint --cov-report=term-missing
ruff format --check .
ruff check .
pyright
```

A diagnostic behavior change without tests and docs is not complete.
