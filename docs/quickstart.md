# Quickstart

## Install

```bash
python -m pip install scieqlint
```

For local development from this repository:

```bash
python -m pip install -e '.[dev]'
```

## Run

```bash
scieqlint check .
```

SciEqLint checks supported scientific document sources:

- `.md`
- `.markdown`
- `.tex`
- `.ipynb`

## Output formats

Supported reporter formats:

```bash
scieqlint check . --format text
scieqlint check . --format json
```

```bash
scieqlint check . --format github
```

```bash
scieqlint check . --format sarif --output scieqlint.sarif
```

Graph JSON exports equation-label nodes and supported reference edges:

```bash
scieqlint graph . --output scieqlint-graph.json
```

## Generated MyST docs

For generated Markdown/MyST pipelines, see the GitHub Actions check step and
preset setup instructions in the
[integration guide](integrations/github-annotations.md#generated-myst-job-step).
The preset includes source-only suspicious-formula checks. Python callers can enable
provenance-backed comparisons by attaching an explicit `SourceOrigin`.

## Demo

```bash
scieqlint demo
```

The demo shows the first two checks: a false scalar identity and a missing equation reference.
