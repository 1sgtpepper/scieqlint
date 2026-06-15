# SARIF

SARIF starts in v0.1.5. It is a reporter and must not change analysis behavior.

```bash
scieqlint check "docs/**/*.md" --format sarif --output scieqlint.sarif
```

SARIF output fails deterministically if a result would exceed the reporter's result
limit. Split the input set or fix broad warning sources before upload.

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
  - run: python -m pip install scieqlint==1.1.0
  - run: scieqlint check "docs/**/*.md" --format sarif --output scieqlint.sarif
  - uses: github/codeql-action/upload-sarif@v4
    with:
      sarif_file: scieqlint.sarif
      category: scieqlint-docs
```

Thin Action wrapper example:

```yaml
permissions:
  contents: read
  security-events: write

steps:
  - uses: actions/checkout@v6
  - uses: Kuhai9801/scieqlint@v1.1.0
    with:
      args: check "docs/**/*.md" "docs/**/*.ipynb" --format sarif --output scieqlint.sarif
  - uses: github/codeql-action/upload-sarif@v4
    with:
      sarif_file: scieqlint.sarif
      category: scieqlint-docs
```

The wrapper is intentionally thin: it sets up Python, installs SciEqLint, and runs
the CLI arguments from `args`. SARIF upload stays in `github/codeql-action/upload-sarif`.
