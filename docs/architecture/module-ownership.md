# Module Ownership

This R1-002A map is the reviewed package boundary artifact for the current
repository tree. Its input boundary is limited to the checked-in
`src/scieqlint` tree, architecture-owned tool and test categories, the
[normative import rules](https://github.com/1sgtpepper/scieqlint/blob/main/SPEC.md#6-architecture),
and the R1-002B import-linter baseline issue. It does not rename packages, change
public behavior, or edit executable import-linter configuration.

The required output is one ownership map that records the current owner,
durable architecture owner, allowed dependency direction, forbidden dependency
direction, temporary CompatibilityShell status, and every temporary exception
with an owner plus retirement issue. Planned packages are marked planned and
are not presented as current code.

Retirement issues are named by their architecture-pack issue IDs because this
documentation slice does not create or update GitHub issues.

## Import-Linter Contracts

The R1-002B executable baseline covers the first three contracts. The remaining
rows record later boundary gates that require their own focused migration. Target
names use the `Owner: architecture boundary map` prefix so failure output
identifies the owning boundary.

| Contract name | Status | Owning boundary | Forbidden direction covered |
|---|---|---|---|
| `Owner: architecture boundary map - CLI must not import internal analysis layers directly` | Current baseline | CLI/API compatibility | `scieqlint.cli` -> `scieqlint.scan`, `scieqlint.parse`, `scieqlint.check` |
| `Owner: architecture boundary map - Reporters render only diagnostics` | Current baseline | SchemaHost projections | `scieqlint.report` -> `scieqlint.io`, `scieqlint.source`, `scieqlint.scan`, `scieqlint.parse`, `scieqlint.check`, `scieqlint.frontend`, `scieqlint.engine` |
| `Owner: architecture boundary map - Engines consume query facts only` | Current baseline | EngineHost | `scieqlint.engine` -> `scieqlint.scan`, `scieqlint.frontend`, `scieqlint.io`, `scieqlint.source`, `scieqlint.report`, `scieqlint.cli`, `scieqlint.app`, `scieqlint.api` |
| `Owner: architecture boundary map - Config must not import runtime analysis or presentation layers` | Future extension | ConfigHost | `scieqlint.config` -> `scieqlint.cli`, `scieqlint.scan`, `scieqlint.parse`, `scieqlint.check`, `scieqlint.report` |
| `Owner: architecture boundary map - Resources must not import runtime analysis or presentation layers` | Future extension | ResourceHost | `scieqlint.io.resources` -> `scieqlint.cli`, `scieqlint.scan`, `scieqlint.parse`, `scieqlint.check`, `scieqlint.report` |
| `Owner: architecture boundary map - Scanners must not import parser checker or reporter layers` | Future extension | FrontendHost | `scieqlint.scan` -> `scieqlint.parse`, `scieqlint.check`, `scieqlint.report` |
| `Owner: architecture boundary map - Parsers must not import scanners checks reporters config loaders or SymPy` | Future extension | MathHost | `scieqlint.parse` -> `scieqlint.scan`, `scieqlint.check`, `scieqlint.report`, `scieqlint.config.load`, `sympy` |
| `Owner: architecture boundary map - Checkers must not import scanner discovery reporter or CLI layers` | Future extension after legacy scanner DTO migration | EngineHost | `scieqlint.check` -> `scieqlint.scan`, `scieqlint.io.discover`, `scieqlint.report`, `scieqlint.cli` |

## Current Source Ownership

| Package or category | Current owner | Durable architecture owner | Allowed dependencies | Forbidden dependencies | CompatibilityShell status | Temporary exceptions |
|---|---|---|---|---|---|---|
| `scieqlint.__init__`, `scieqlint.__main__`, `scieqlint.py.typed` | package metadata and module entry shim | CLI/API compatibility | `cli` entry point only | analysis internals from package metadata | Not CompatibilityShell | None |
| `scieqlint.api` | public Python API facade | Public API and AnalysisSession | `app`, `config`, `diag`, public result/source models | scanner/parser/checker internals except through session/app facade | CompatibilityShell adapter until AnalysisSession owns public entry points | Owner: CLI/API compatibility; retire in R2-133A/R2-133B |
| `scieqlint.app` | current orchestration service | AnalysisSession | `io`, `scan`, `parse`, `check`, `report`, `config`, `diag`, `graph`, `schema` | CLI command parsing and reporter-specific side effects outside orchestration | CompatibilityShell service facade | Owner: AnalysisSession; retire in R1-054A/R1-054B |
| `scieqlint.cli` | command-line plumbing | CLI/API compatibility | `api`, config loading options, reporter selection, exit handling | direct `scan`, `parse`, `check` imports | CompatibilityShell entry point | Owner: CLI/API compatibility; indirect analysis access through facade remains allowed until R2-134A/R2-134B; enforced by `Owner: architecture boundary map - CLI must not import internal analysis layers directly` |
| `scieqlint.config` | config models, presets, load, validation | ConfigHost | standard library, `diag.model`, local config modules, package resources | `cli`, `scan`, `parse`, `check`, `report` | Not CompatibilityShell | Narrow temporary exception: `config.load` may import `io.identity` only to capture the descriptor identity of a config file while parsing it; retire under R1-013/R1-014/R1-015. |
| `scieqlint.diag` | diagnostic models, catalog, DiagnosticIR bridge | DiagnosticHost | source-span values, severity/catalog data, public projection helpers | scanner discovery, parser execution, checker orchestration, reporters | Not CompatibilityShell | None |
| `scieqlint.engine` | current analysis engine interfaces and rule runners | EngineHost | `facts`, `query`, `diag.ir`, `policy`, public source/query values | `cli`, `app`, `api`, `io`, `source`, `scan`, `frontend`, `report` | Not CompatibilityShell | No temporary exception; R1-002B contract `Owner: architecture boundary map - Engines consume query facts only`; PolicyHost supplies catalog-backed severity and output-profile policy. |
| `scieqlint.examples` | packaged demo documents | ResourceHost | package data only | runtime imports from analysis, CLI, or reporting layers | Not CompatibilityShell | None |
| `scieqlint.facts` | immutable fact records and snapshots | FactHost | dataclasses, typing, `io.source` document value when needed | scanner/parser/checker execution, reporters, CLI | Not CompatibilityShell | None |
| `scieqlint.frontend` | MyST token lowering and structure extraction helpers | FrontendHost | `facts`, `ir`, `diag`, `source`, injected `io.workspace` path identity, narrow markdown-it token APIs | `check`, `report`, `cli`; direct engine orchestration | Not CompatibilityShell | `WorkspaceHost` is injected by orchestration; frontends do not discover or read files. |
| `scieqlint.graph` | graph model, JSON projection, export helpers | GraphHost | `facts`, `query`, `diag`, schema/public projection values, pure `io.workspace` path normalization | scanner/parser/checker execution, CLI | Not CompatibilityShell | Graph export receives the project root and performs no discovery or file reads. |
| `scieqlint.io` except `io.resources` | discovery, limits, source loading, and canonical project-member identity | WorkspaceHost | path policy, source documents, config values, resource helpers | `scan`, `parse`, `check`, `report`, `cli` unless explicitly orchestrated by `app` | Not CompatibilityShell | Application-injected `WorkspaceHost` is the shared path-identity owner; normalized member collisions are rejected here. |
| `scieqlint.io.resources` | packaged resource loading | ResourceHost | `importlib.resources`, package data paths | `cli`, `scan`, `parse`, `check`, `report` | Not CompatibilityShell | No temporary exception; future contract `Owner: architecture boundary map - Resources must not import runtime analysis or presentation layers` |
| `scieqlint.ir` | DocumentIR and FrontendResult values | ImmutableSource and FrontendHost boundary | `io.source`, immutable fact values | scanner execution, parser execution, checkers, reporters, CLI | Not CompatibilityShell | None |
| `scieqlint.parse` | math grammar, AST, parser, normalization, printing | MathHost | `parse.ast`, `diag.model`, source-span types, Lark adapter | `scan`, `check`, `report`, `config.load`, SymPy | Not CompatibilityShell | No temporary exception; future contract `Owner: architecture boundary map - Parsers must not import scanners checks reporters config loaders or SymPy` |
| `scieqlint.policy` | output-profile support and diagnostic severity selection | PolicyHost preview | `facts`, `diag.catalog`, `diag.model` | `frontend`, `scan`, `parse`, `check`, `report`, `cli`, `app`, `api` | Not CompatibilityShell | Preview scope only; suppression and baseline migration remain owned by R1-021A/R1-021B/R1-022/R1-023/R1-024. |
| `scieqlint.presets` | packaged preset data | PackHost planned data | package data only | runtime imports from CLI, analysis, or reporting layers | Not CompatibilityShell | Owner: PackHost; retire package-data-only placeholder under R3-146A/R3-149A |
| `scieqlint.query` | read-only views over FactSnapshot | QueryHost | `facts`, immutable query helpers, pure `io.workspace` path normalization, standard library | scanners, parsers, checkers, reporters, CLI | Not CompatibilityShell | Query code may normalize stored paths but does not discover or read files. |
| `scieqlint.report` | text, JSON, GitHub, SARIF renderers | SchemaHost projections | `diag.model`, versioned `schema` projection values, packaged schema metadata | `io` source loading, `source`, `scan`, `frontend`, `parse`, `check`, `engine` | Not CompatibilityShell | No temporary exception; R1-002B contract `Owner: architecture boundary map - Reporters render only diagnostics` |
| `scieqlint.scan` | current Markdown, LaTeX, notebook, and symbol scanners | FrontendHost | `io.source`, injected `io.workspace` path identity, `diag.model`, `scan.base`, source-map/value helpers | `parse`, `check`, `report` | Transitional scanner facade for durable FrontendResult lowering | `WorkspaceHost` is injected by orchestration; scanners do not discover or read files. |
| `scieqlint.schema` | result model and versioned diagnostic projection seam | SchemaHost | `diag`, `facts`, public projection values | scanners, parsers, checkers, CLI | Not CompatibilityShell | Owner: SchemaHost; retire ad hoc registry shape under R1-049 |
| `scieqlint.schemas` | packaged JSON Schema files | SchemaHost | package data only | runtime imports from analysis, CLI, or reporting layers | Not CompatibilityShell | None |
| `scieqlint.source` | current source map helpers | ImmutableSource | `io.source`, diagnostic span values | workspace discovery, scanners, parsers, checkers, reporters, CLI | Not CompatibilityShell | Owner: ImmutableSource; retire incomplete canonical URI coverage under R1-005A/R1-005B |
| `scieqlint.check` | current algebra, references, dimensions, symbols, suppressions | EngineHost | `parse.ast`, `diag`, `config.model`, `facts`, `query`, `graph` when graph exists, pure `io.workspace` path normalization | `scan`, `io.discover`, `report`, `cli` | Transitional checker facade for durable engines | Compatibility reference checks normalize caller-provided paths but do not discover or read files. |

## Architecture-Owned Tool And Test Categories

| Package or category | Current owner | Durable architecture owner | Allowed dependencies | Forbidden dependencies | CompatibilityShell status | Temporary exceptions |
|---|---|---|---|---|---|---|
| `tools/architecture/terminology_drift.py` | deterministic architecture terminology drift scanner | Architecture conformance tooling | approved ownership map, import-linter config, committed fixtures | production analysis semantics, broad allowlists, unowned baselines | Not CompatibilityShell | Owner: Architecture conformance tooling; release-blocking gate in `.github/workflows/ci.yml` |
| `tests/test_architecture_contracts.py` | architecture contract tests | Architecture conformance tooling | public contract fixtures and stable host APIs | private behavior changes unrelated to architecture assertions | Not CompatibilityShell | None |
| `tests/test_contract_readiness.py` | v1.0.0 release readiness assertions | Release gate tooling | docs, public APIs, packaged schemas, CLI command names | implementation-only internals unless required by a readiness assertion | Not CompatibilityShell | None |
| Other `tests/test_*.py` | feature-owned tests | Matching package or host owner under test | public APIs, focused internal helpers for the owning feature | cross-layer imports that hide ownership violations | Not CompatibilityShell | Owner: touched feature owner; retire compatibility-path imports in the same issue that retires the matching production compatibility path |
| `tests/fixtures` | committed test inputs | Corpus and fixture governance | static fixture data | generated state that is not reproducible from tests | Not CompatibilityShell | None |
| `tests/golden` | committed expected outputs | Golden-output and schema compatibility governance | deterministic expected output data | advisory or environment-dependent fields | Not CompatibilityShell | None |

## Planned Packages

These architecture owners are planned names or durable ownership concepts, not
current top-level `src/scieqlint` packages unless listed above.

| Planned package or owner | Current status | Durable owner | Retirement or creation issue |
|---|---|---|---|
| `AnalysisSession` facade | Planned durable replacement for `app` orchestration | AnalysisSession | R1-053, R1-054A/R1-054B |
| `CompatibilityShell` adapters | Architecture role, not a package | CLI/API compatibility | R2-133A/R2-133B and R2-134A/R2-134B retire legacy entry behavior |
| `WorkspaceHost` | Architecture role currently represented by `io` | WorkspaceHost | R1-013/R1-014/R1-015 |
| `ImmutableSource` expanded model | Architecture role currently represented by `io.source` and `source.maps` | ImmutableSource | R1-005A/R1-009A/R1-010A |
| `FrontendResult` durable lowering path | Current value exists in `ir`; full cutover planned | FrontendHost | R1-029/R1-031B/R1-032B |
| `FactSnapshot` builder/indexing | Current facts and query values exist; builder/indexing completion planned | FactHost and QueryHost | R1-037A/R1-037B/R1-040/R1-041A/R1-041B |
| `PolicyHost` expanded policy | Current preview package owns output-profile support and diagnostic severity selection; suppression and baseline migration remain planned | PolicyHost | R1-021A/R1-021B/R1-022/R1-023/R1-024 |
| `SchemaHost` registry | Current `schema`/`schemas` exist; registry ownership planned | SchemaHost | R1-049/R1-050/R1-051/R1-052 |
| `PackHost` registry | Current `presets` data exists; registry planned | PackHost | R3-146A/R3-149A |
