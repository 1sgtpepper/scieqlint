# Roadmap

SciEqLint grows by narrow, release-gated slices. A release date does not move because a nice-to-have is unfinished. Scope is cut before dates move. Dates move only for correctness, security, packaging, or trust defects.

## Release ladder

| Release | Time box | User-facing reason | Ships | Does not ship |
|---|---:|---|---|---|
| v0.0.1 | 1 week | installable skeleton | package, CLI shell, config defaults, CI skeleton | real checks |
| v0.1.0 | 4 weeks | catch bad equations and broken refs in Markdown/MyST | Markdown/MyST scanner subset, references, parser, algebra, text, JSON, schemas, demo | dimensions, LaTeX, notebooks, GitHub annotations, SARIF |
| v0.1.1 | 1 week | make PR annotations easy | GitHub reporter, pre-commit metadata, CI docs | new math behavior |
| v0.1.2 | 2 weeks | catch configured dimension mistakes | dimension engine and config | presets, aliases, unit database |
| v0.1.3 | 2 weeks | support LaTeX source files | LaTeX containers, labels, references | full LaTeX parser, macro expansion |
| v0.1.4 | 1 week | support notebook Markdown cells | `.ipynb` Markdown-cell scanning | notebook execution, code-cell analysis |
| v0.1.5 | 1 week | support code scanning | SARIF reporter and thin Action wrapper | new scanner/math behavior |
| v0.2.0 | 3 weeks | fit serious docs workflows | suppressions, presets, aliases, maybe scalar functions | graph, symbol inference |
| v0.3.0 | 2 weeks | make equations navigable | graph JSON export | natural-language symbol parsing |
| v0.4.0 | 3 weeks | catch undefined symbols and notation drift | explicit symbol directives and checks | prose inference |
| v0.5.0 | 4 weeks | run well on books/sites | project mode, baselines, file ordering | plugin API |
| v0.9.0 | 4 weeks | stabilize contracts | performance, compatibility, contract candidates | large new features |
| v1.0.0 | acceptance-gated | stable scientific CI core | frozen CLI/JSON/SARIF/config/API | experimental defaults |

## Scope rule

At the start of each release, every issue must be marked as one of:

- `required`: needed for the release promise,
- `cuttable`: may be deferred without breaking the promise,
- `forbidden`: belongs to a later release.

A release must not absorb the next release's features to feel bigger.
