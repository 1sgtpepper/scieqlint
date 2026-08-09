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
suffixes, during `pre-commit` and `pre-push`. For an ordinary commit it inspects the
staged diff; for a run that supplies a revision range, including the usual ref-range
and pre-push runs, it inspects that range so deleted and rename-source paths remain
visible. Explicit filename runs use the filenames supplied by pre-commit. Unrelated
changes still skip the project check.

An initial `pre-push` with no previous ref uses pre-commit's all-files candidate set
instead of a revision range.

When a supported change is present, the adapter runs a complete project-context check
rather than passing candidate filenames as checker input; configuration, ignore rules,
baselines, project ordering, and cross-file references remain available. Options before
the `--` boundary are passed to `scieqlint check`, while filenames after it are used
only to decide whether the project check should run. Consumers overriding the hook's
`args` must preserve that boundary, for example `args: [--strict-unknowns, --]`;
configurations without it fail explicitly.
