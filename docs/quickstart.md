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

v0.1.0 checks Markdown/MyST files only:

- `.md`
- `.markdown`

## Output formats

v0.1.0 ships:

```bash
scieqlint check . --format text
scieqlint check . --format json
```

Later releases add GitHub annotations and SARIF.

## Demo

```bash
scieqlint demo
```

The demo shows the first two checks: a false scalar identity and a missing equation reference.
