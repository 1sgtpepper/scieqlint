# pre-commit

v0.1.1 adds pre-commit metadata.

```yaml
repos:
  - repo: https://github.com/Kuhai9801/scieqlint
    rev: v1.1.0
    hooks:
      - id: scieqlint
```

The hook is triggered by `.md`, `.markdown`, `.tex`, and `.ipynb` files, including
uppercase suffixes. It runs one project-context check rather than passing only
the staged filenames, so configuration, includes, baselines, and cross-file
references remain available. The explicit `--` also keeps option-shaped paths
from being interpreted as CLI options.
