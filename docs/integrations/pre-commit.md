# pre-commit

v0.1.1 adds pre-commit metadata.

```yaml
repos:
  - repo: https://github.com/Kuhai9801/scieqlint
    rev: v1.1.0
    hooks:
      - id: scieqlint
```

The hook checks `.md`, `.markdown`, `.tex`, and `.ipynb` changes, including uppercase
suffixes. It is invoked for every pre-commit run so deletion-only and
supported-to-unsupported rename changes cannot be filtered out before the hook sees
them. Its adapter then filters both candidate paths and the staged diff, so unrelated
commits still skip the project check. When a supported change is present, it runs one
project-context check rather than passing staged filenames as CLI input; configuration,
ignore rules, baselines, project ordering, and cross-file references remain available.
The explicit `--` keeps the project check's path boundary filename-safe.
