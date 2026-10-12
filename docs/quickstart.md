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

For generated Markdown/MyST output, materialize the generated-document preset and
run the normal checker with that config:

```bash
scieqlint init --preset generated-myst --path scieqlint.generated-myst.toml
scieqlint check "docs/**/*.md" --config scieqlint.generated-myst.toml --format github
```

The preset selects the generated-document profile and supplies its scanner/parser
defaults, including source-only suspicious-formula checks. Provenance-backed
comparisons are available to Python callers that attach an explicit `SourceOrigin`.

## Demo

```bash
scieqlint demo
```

The demo shows the first two checks: a false scalar identity and a missing equation reference.
