# Roadmap

SciEqLint grows by scoped release slices. Release order changes only for correctness, security, packaging, or compatibility defects.

## Release ladder

| Release | User-facing reason | Ships |
|---|---|---|
| v0.0.1 | installable skeleton | package, CLI shell, config defaults, CI skeleton |
| v0.1.0 | catch bad equations and broken refs in Markdown/MyST | Markdown/MyST scanner subset, references, parser, algebra, text, JSON, schemas, demo |
| v0.1.1 | make PR annotations easy | GitHub reporter, pre-commit metadata, CI docs |
| v0.1.2 | catch configured dimension mistakes | dimension engine and config |
| v0.1.3 | support LaTeX source files | LaTeX containers, labels, references |
| v0.1.4 | support notebook Markdown cells | `.ipynb` Markdown-cell scanning |
| v0.1.5 | support code scanning | SARIF reporter and thin Action wrapper |
| v0.2.0 | fit serious docs workflows | suppressions, presets, aliases, maybe scalar functions |
| v0.3.0 | make equations navigable | graph JSON export |
| v0.4.0 | catch undefined symbols and notation drift | explicit symbol directives and checks |
| v0.5.0 | run well on books/sites | project mode, baselines, file ordering |
| v0.9.0 | stabilize contracts | performance, compatibility, contract candidates |
| v1.0.0 | stable scientific CI core | frozen CLI/JSON/SARIF/config/API |
| v1.1.0 | validate generated MyST/scientific docs | MyST structure and generic-reference diagnostics, generated-output anchor audit, generated-MyST preset |

## Scope rule

At the start of each release, every issue must be marked as one of:

- `required`: needed for the release scope,
- `cuttable`: may be deferred without breaking the release scope,
- `later`: belongs to a later release.

A release keeps unrelated surfaces outside the active release scope.
