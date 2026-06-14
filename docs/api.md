# Public API

The stable API surface is exported from `scieqlint.api`:

- `check_paths(paths, *, config_path=None, no_algebra=False, inline_math=False,
  strict_unknowns=False, absolute_paths=False)`
- `check_documents(documents, *, config)`
- `graph_paths(paths, *, config_path=None)`
- `graph_documents(documents, *, config)`
- `load_config(path=None, *, preset=None)`

Public API usage:

```python
from pathlib import Path
from scieqlint.api import (
    check_documents,
    check_paths,
    graph_documents,
    graph_paths,
    load_config,
)

config = load_config(Path("scieqlint.toml"))
result = check_paths([Path("README.md")], config_path=Path("scieqlint.toml"))
graph = graph_paths([Path("README.md")], config_path=Path("scieqlint.toml"))
print(result.exit_code())
```

API calls must not print to stdout/stderr and must not call `sys.exit`.
`check_paths` is the path-based API and applies project discovery, config lookup,
file ordering, ignore rules, source loading, and diagnostic baselines.
`check_documents` and `graph_documents` are the already-loaded-document APIs and
do not read baseline files from disk.

`CheckResult` exposes `diagnostics`, `files_checked`, `math_blocks_checked`,
`config_path`, `version`, `show_suppressed`, and `exit_code()`. `exit_code()`
returns `1` only when an unsuppressed error diagnostic exists.

`Diagnostic` exposes stable diagnostic data used by reporters and JSON output:
`code`, `severity`, `message`, `span`, `equation`, `detail`, `hint`, `rule`,
`suppressed`, and `suppression_reason`.

`load_config(path, preset="mechanics")` loads packaged preset defaults before the
user config file, so user config values override preset values.

## Architecture-preview API

The architecture-preview API is exported separately from `scieqlint.api`. It is
available for profile and generated-output validation while the stable CLI and
config surfaces continue to use the v1.0 path.

- `analyze_paths_architecture(paths, *, profiles=("scientific-myst",), generated_pairs=())`
- `analyze_documents_architecture(documents, *, profiles=("scientific-myst",), generated_pairs=())`

`scientific-myst` enables deterministic MyST/Markdown structure, generic and
equation reference, and math-container diagnostics. `generated` is a standalone
generated-document validation profile; it includes the scientific MyST rule
families and adds source/generated preservation checks. Generated preservation
checks require explicit `(source_path, generated_path)` pairs.

```python
from pathlib import Path

from scieqlint.api_architecture import analyze_paths_architecture
from scieqlint.schema.json_architecture import render_analysis_result_json

result = analyze_paths_architecture(
    (Path("source"), Path("generated")),
    profiles=("generated",),
    generated_pairs=(
        ("source/jax_intro.md", "generated/jax_intro.md"),
    ),
)

Path("scieqlint-generated.json").write_text(
    render_analysis_result_json(result),
    encoding="utf-8",
)
raise SystemExit(1 if result.summary()["errors"] else 0)
```

The preview result schema is `0.2-architecture-preview`. It is intentionally not
the stable JSON reporter schema, and it does not imply a stable CLI flag or TOML
profile key.
