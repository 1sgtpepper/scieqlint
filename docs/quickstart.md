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

v0.1.0 ships:

```bash
scieqlint check . --format text
scieqlint check . --format json
```

v0.1.1 adds GitHub annotations:

```bash
scieqlint check . --format github
```

v0.1.5 adds SARIF:

```bash
scieqlint check . --format sarif --output scieqlint.sarif
```

Graph JSON exports equation-label nodes and supported reference edges:

```bash
scieqlint graph . --output scieqlint-graph.json
```

## Generated MyST docs

For generated Markdown/MyST output, materialize the packaged preset and run the
normal checker with that config:

```bash
scieqlint init --preset generated-myst --path scieqlint.generated-myst.toml
scieqlint check "docs/**/*.md" --config scieqlint.generated-myst.toml --format github
```

## Demo

```bash
scieqlint demo
```

The demo shows the first two checks: a false scalar identity and a missing equation reference.
