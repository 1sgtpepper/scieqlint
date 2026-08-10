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
`check_paths` and `graph_paths` raise `FileNotFoundError` when an explicitly
provided non-glob path does not exist. Existing paths are treated literally even
when their names contain glob characters; only nonexistent strings with glob
syntax are expanded.
`check_documents` and `graph_documents` are the already-loaded-document APIs and
do not read baseline files from disk. Path-based APIs preserve their analysis result
when output-safety metadata is unavailable; that metadata is required only by the
CLI guard before writing a file output.

Path-based diagnostics and graph spans retain the caller-visible lexical input
spelling. Relative inputs keep that spelling; absolute inputs are rendered
relative to the current working directory by default. For `check_paths()`,
`absolute_paths=True` retains an explicitly absolute input's lexical spelling
without resolving symlinks; `graph_paths()` always uses the default presentation.
When an absolute input and the current directory have different native roots,
default presentation raises `ValueError` rather than leak an absolute path or
collapse distinct roots. Checks may opt into absolute paths; graph inputs must be
expressed on the current root.

`CheckResult` exposes `diagnostics`, `files_checked`, `math_blocks_checked`,
`config_path`, `version`, `show_suppressed`, and `exit_code()`. `exit_code()`
returns `1` only when an unsuppressed error diagnostic exists.

`Diagnostic` exposes stable diagnostic data used by reporters and JSON output:
`code`, `severity`, `message`, `span`, `equation`, `detail`, `hint`, `rule`,
`suppressed`, and `suppression_reason`.

`load_config(path, preset="generated-myst")` or
`load_config(path, preset="mechanics")` loads packaged preset defaults before
the user config file, so user config values override preset values.
