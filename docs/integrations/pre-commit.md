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
suffixes, during ordinary `pre-commit` runs. It keeps pre-commit's candidate selection
authoritative for existing paths, including explicit `--files`, `exclude`, `types`, and
`exclude_types` selections. When pre-commit removes every candidate, the adapter
consults the staged diff only for deleted paths and rename sources; those invisible-role
recoveries cannot be suppressed by consumer filters. Ordinary staged modifications do
not bypass candidate selection. Pre-push and generic ref-range runs are rejected because
this adapter does not validate arbitrary revision snapshots.

When a supported change is present, the adapter runs a complete project-context check
rather than passing candidate filenames as checker input; configuration, ignore rules,
baselines, project ordering, and cross-file references remain available. Options before
the `--` boundary are passed to `scieqlint check`, while filenames after it are used
only to decide whether the project check should run. Consumers overriding the hook's
`args` must preserve that boundary, for example `args: [--strict-unknowns, --]`;
configurations without it fail explicitly.
