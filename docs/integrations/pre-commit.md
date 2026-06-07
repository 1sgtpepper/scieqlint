# pre-commit

v0.1.1 adds pre-commit metadata.

```yaml
repos:
  - repo: https://github.com/Kuhai9801/scieqlint
    rev: v0.1.1
    hooks:
      - id: scieqlint
```

The v0.1.1 hook targets only `.md` and `.markdown`. Later releases expand to `.tex` and `.ipynb`.
