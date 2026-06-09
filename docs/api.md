# Public API

Public API usage:

```python
from pathlib import Path
from scieqlint.api import check_paths, graph_paths, load_config

config = load_config(Path("scieqlint.toml"))
result = check_paths([Path("README.md")], config_path=Path("scieqlint.toml"))
graph = graph_paths([Path("README.md")], config_path=Path("scieqlint.toml"))
print(result.exit_code())
```

API calls must not print to stdout/stderr and must not call `sys.exit`.
`CheckResult.show_suppressed` records the loaded report setting used by the JSON
reporter to decide whether suppressed diagnostics are included.

`load_config(path, preset="mechanics")` loads packaged preset defaults before the
user config file, so user config values override preset values.
