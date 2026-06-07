# Public API

v0.1.0 public API:

```python
from pathlib import Path
from scieqlint.api import check_paths, load_config

config = load_config(Path("scieqlint.toml"))
result = check_paths([Path("README.md")], config_path=Path("scieqlint.toml"))
print(result.exit_code())
```

API calls must not print to stdout/stderr and must not call `sys.exit`.
