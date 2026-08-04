# SARIF

SARIF starts in v0.1.5. It is a reporter and must not change analysis behavior.

```bash
scieqlint check "docs/**/*.md" --format sarif --output scieqlint.sarif
```

SARIF output uses URI-encoded artifact paths and declares columns as Unicode code
points. It also fails deterministically if a result would exceed the reporter's
result limit; split the input set or fix broad warning sources before upload.

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
  - run: set +e; scieqlint check "docs/**/*.md" --format sarif --output scieqlint.sarif; status=$?; test "$status" -le 1 || exit "$status"
  - run: test -s scieqlint.sarif && python -m json.tool scieqlint.sarif >/dev/null
  - uses: github/codeql-action/upload-sarif@v4
    with:
      sarif_file: scieqlint.sarif
      category: scieqlint-docs
```

The status guard allows findings (exit 1) to reach the upload step while
preserving other exit statuses. The artifact check rejects missing, empty, or
invalid JSON reports before the uploader runs. The example pins the published
`1.1.0` release; releases with the distinct operational exit-2 contract retain
that status through the guard.

The thin GitHub Action runs the CLI directly and does not normalize a findings
exit code, so use the direct workflow above when findings must still reach the
upload step.
