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
suffixes, during ordinary `pre-commit` runs. It reads the complete staged Git diff once,
including deleted paths and both sides of renames, and runs one complete project-context
check when any changed path has a supported suffix. Unsupported staged changes skip the
check. Pre-push and generic ref-range runs are rejected because this adapter does not
validate arbitrary revision snapshots.

The hook deliberately does not receive pre-commit candidate filenames. Consequently,
consumer `--files`, `exclude`, `types`, and `exclude_types` settings do not scope this
staged-index check. The checker still receives project configuration, ignore rules,
baselines, project ordering, and cross-file references. Options before the `--` boundary
are passed to `scieqlint check`; filenames after the boundary are rejected. Consumers
overriding the hook's `args` must preserve the boundary, for example
`args: [--strict-unknowns, --]`.
