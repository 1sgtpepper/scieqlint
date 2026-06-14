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

## Generated-output preview

Generated Markdown/MyST validation is available through the architecture-preview
profile path. The `generated` profile checks deterministic source-generated
document facts and exits non-zero when error diagnostics are found.

```bash
scieqlint check source generated \
  --profile generated \
  --generated-pair source/page.md=generated/page.md \
  --format github
```

The same profile can be selected from `scieqlint.toml`:

```toml
[architecture]
profiles = ["generated"]
generated_pairs = ["source/page.md=generated/page.md"]
```

GitHub Actions can run the same preview gate after a translation, OCR, or
documentation-generation step:

```yaml
- name: Validate generated scientific Markdown
  run: |
    scieqlint check source generated \
      --profile generated \
      --generated-pair source/page.md=generated/page.md \
      --format github
```

Use `--profile scientific-myst --profile strict-ci` for scientific MyST
repositories that should fail CI on profile-selected warnings.

## Demo

```bash
scieqlint demo
```

The demo shows the first two checks: a false scalar identity and a missing equation reference.
