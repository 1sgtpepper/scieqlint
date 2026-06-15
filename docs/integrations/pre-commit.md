# pre-commit

v0.1.1 adds pre-commit metadata.

```yaml
repos:
  - repo: https://github.com/Kuhai9801/scieqlint
    rev: v1.1.0
    hooks:
      - id: scieqlint
```

The hook targets `.md`, `.markdown`, `.tex`, and `.ipynb` files.
