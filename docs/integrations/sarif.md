# SARIF

SARIF starts in v0.1.5. It is a reporter and must not change analysis behavior.

```bash
scieqlint check "docs/**/*.md" --format sarif --output scieqlint.sarif
```

GitHub upload example:

```yaml
permissions:
  contents: read
  security-events: write

steps:
  - uses: actions/checkout@v6
  - uses: actions/setup-python@v6
    with:
      python-version: "3.11"
  - run: python -m pip install scieqlint==0.1.5
  - run: scieqlint check "docs/**/*.md" --format sarif --output scieqlint.sarif
  - uses: github/codeql-action/upload-sarif@v4
    with:
      sarif_file: scieqlint.sarif
      category: scieqlint-docs
```
