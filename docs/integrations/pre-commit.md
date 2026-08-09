# pre-commit

v0.1.1 adds pre-commit metadata.

```yaml
repos:
  - repo: https://github.com/Kuhai9801/scieqlint
    rev: v1.1.0
    hooks:
      - id: scieqlint
```

During ordinary `pre-commit` runs, the hook runs one complete project-context check per
invocation. This includes normal commits, clean `--all-files` runs, explicit `--files`
runs, and commits whose staged changes do not include a supported source. Pre-commit
stashes unstaged worktree changes before invoking the hook, so the check observes the
staged project snapshot. Pre-push and generic ref-range runs are rejected because this
adapter does not validate arbitrary revision snapshots.

The hook deliberately does not receive pre-commit candidate filenames because each
invocation must run exactly once. Consumer `--files`, `exclude`, `types`, and
`exclude_types` settings therefore do not scope the project check. The checker still
receives project configuration, ignore rules, baselines, project ordering, and
cross-file references. Options before the `--` boundary are passed to `scieqlint check`;
filenames after the boundary are rejected. Consumers overriding the hook's `args` must
preserve the boundary, for example `args: [--strict-unknowns, --]`.
