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

Later releases add SARIF.

## Demo

```bash
scieqlint demo
```

The demo shows the first two checks: a false scalar identity and a missing equation reference.
