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

Generated Markdown/MyST validation is currently available through the
architecture-preview API, not through a stable `scieqlint check --profile` flag
or `scieqlint.toml` key. The `generated` profile checks deterministic
source-generated document facts and exits non-zero when error diagnostics are
found.

```python
from pathlib import Path

from scieqlint.api_architecture import analyze_paths_architecture
from scieqlint.schema.json_architecture import render_analysis_result_json

result = analyze_paths_architecture(
    (Path("source"), Path("generated")),
    profiles=("generated",),
    generated_pairs=(("source/page.md", "generated/page.md"),),
)
Path("scieqlint-generated.json").write_text(
    render_analysis_result_json(result),
    encoding="utf-8",
)
raise SystemExit(1 if result.summary()["errors"] else 0)
```

GitHub Actions can run the same preview gate after a translation, OCR, or
documentation-generation step:

```yaml
- name: Validate generated scientific Markdown
  run: |
    python - <<'PY'
    from pathlib import Path

    from scieqlint.api_architecture import analyze_paths_architecture
    from scieqlint.schema.json_architecture import render_analysis_result_json

    result = analyze_paths_architecture(
        (Path("source"), Path("generated")),
        profiles=("generated",),
        generated_pairs=(("source/page.md", "generated/page.md"),),
    )
    Path("scieqlint-generated.json").write_text(
        render_analysis_result_json(result),
        encoding="utf-8",
    )
    raise SystemExit(1 if result.summary()["errors"] else 0)
    PY
```

The stable GitHub annotation reporter can still be run over generated files as a
separate check, but it does not yet consume the architecture-preview generated
profile or source/generated pairing metadata.

## Demo

```bash
scieqlint demo
```

The demo shows the first two checks: a false scalar identity and a missing equation reference.
