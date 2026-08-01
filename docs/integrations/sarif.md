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
  - run: rm -f scieqlint.sarif
  - run: scieqlint check "docs/**/*.md" --format sarif --output scieqlint.sarif || test "$?" -eq 1
  - run: test -s scieqlint.sarif
  - uses: github/codeql-action/upload-sarif@v4
    with:
      sarif_file: scieqlint.sarif
      category: scieqlint-docs
```

The status guard allows findings (exit 1) to reach the upload step while
preserving operational failures (exit 2). The non-empty-file check prevents an
operational failure that produced no report from reaching the uploader. Pin a
SciEqLint release that provides this `0`/`1`/`2` exit-code contract; the
historical `1.1.0` release does not.

The thin GitHub Action runs the CLI directly and does not normalize a findings
exit code. It is therefore not a SARIF-upload wrapper: use the direct workflow
above when findings must still reach the upload step.
