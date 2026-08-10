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
runs, and commits whose staged changes do not include a supported source. For a normal
commit hook invocation, pre-commit temporarily removes tracked unstaged changes before
the check; untracked supported files remain visible to project discovery. `--all-files`
and `--files` runs do not stash unstaged changes, so those modes check the current
worktree instead.

The hook deliberately does not receive pre-commit candidate filenames because each
invocation must run exactly once. Consumer `--files`, `exclude`, `types`, and
`exclude_types` settings therefore do not scope the project check. The checker still
receives project configuration, ignore rules, baselines, project ordering, and
cross-file references. The adapter validates the pre-boundary arguments with the `check`
command parser; positional paths before or after the `--` boundary are rejected. Consumers
overriding the hook's `args` must
preserve the boundary, for example `args: [--strict-unknowns, --]`. The published hook
is eligible only for the `pre-commit` stage and requires pre-commit 3.2.0 or newer;
pre-push and generic revision-range runs are not supported because the adapter does not
validate arbitrary revision snapshots. Python isolated mode ignores inherited Python path
variables and prevents a consumer-side `scieqlint.py` or `scieqlint/` package from shadowing
the installed hook package.
