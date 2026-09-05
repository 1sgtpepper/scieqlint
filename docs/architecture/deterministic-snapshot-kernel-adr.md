# ADR R1-001: Deterministic Snapshot Kernel

Status: Ratified for R1 architecture governance
Decision date: 2026-06-26
Owner: Architecture governance
Traceability issue: [GitHub #133](https://github.com/1sgtpepper/scieqlint/issues/133)

## Decision

SciEqLint selects the Deterministic Snapshot Kernel as the durable architecture for
R1 and later work. The selected architecture is a functional core where frontends
lower source documents into immutable facts, a snapshot owns the stable analysis
state, query views expose read-only indexes, engines consume only query views, and
projection hosts serialize public results.

The current repository already has preview implementations for immutable facts,
`FactSnapshot`, `QueryHost`, several query views, architecture contract tests, and
initial import-linter contracts. It does not yet have the complete host package
split, complete release-gate toolchain, complete digest contract, or final
CompatibilityShell retirement path. Those items are planned follow-up issues and
must not be described as current code.

The current R1 governance evidence is recorded by the merged [PR #216](https://github.com/1sgtpepper/scieqlint/pull/216),
[PR #217](https://github.com/1sgtpepper/scieqlint/pull/217),
[PR #218](https://github.com/1sgtpepper/scieqlint/pull/218),
[PR #219](https://github.com/1sgtpepper/scieqlint/pull/219), and
[PR #220](https://github.com/1sgtpepper/scieqlint/pull/220). The later ownership-map
synchronization is recorded by merged [PR #289](https://github.com/1sgtpepper/scieqlint/pull/289).
These links identify completed evidence; they do not turn the remaining host migrations
into current code.

## Scope

This decision record accepts only architecture documents, the module graph, and
CI/import configuration as inputs. Its required output is this reviewed ADR and
architecture decision log artifact. It does not change runtime code, CLI/API
signatures, diagnostics, schemas, ordering behavior, discovery, baselines, or
suppressions.

The R1 workstream tracker is [GitHub #132](https://github.com/1sgtpepper/scieqlint/issues/132).
Repository-file links in this ADR are pinned to the reviewed `origin/main` revision
[`e7dbb1f2cdae2485c4027fc8c415da25c0ef9663`](https://github.com/1sgtpepper/scieqlint/commit/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663),
and tracker links use the current repository owner. R2/R3 work is not linked here until
a uniquely scoped GitHub issue exists; future issue numbers are never reserved.

The kernel's total ordering key is:

```text
KernelOrderKey = (canonical_uri, source_start, source_end, owner_phase, stable_id)
```

Durable implementations must use this key, or a stricter documented projection of
it, whenever equivalent inputs can arrive in shuffled order. Shuffled equivalent
inputs must produce byte-identical machine output after advisory fields explicitly
declared as non-stable are removed.

## Selected Architecture

The normative summary remains [Architecture: Layer rules](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/docs/architecture.md#layer-rules).
This ADR ratifies the durable ownership order below and records which parts are
current, legacy, or planned.

| Order | Durable owner and value | Normative summary | Current repository package | Contract or executable evidence | Release gate or follow-up |
|---|---|---|---|---|---|
| 1 | WorkspaceHost owns workspace discovery, canonical paths, and source loading. | [CLI owns plumbing; scanners do not read files](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/docs/architecture.md#layer-rules) | Current `WorkspaceHost` implementation in [`src/scieqlint/io/workspace.py`](https://github.com/1sgtpepper/scieqlint/blob/6c4a020c739a1fc9516e37255c36df032da3c561/src/scieqlint/io/workspace.py); orchestration injects it into stateful scanners and frontends, while compatibility/query/graph paths use its pure lexical normalizer. | Source/document and path-identity tests in [`tests/test_source.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/tests/test_source.py) and [`tests/test_crossref_path_normalization.py`](https://github.com/1sgtpepper/scieqlint/blob/6c4a020c739a1fc9516e37255c36df032da3c561/tests/test_crossref_path_normalization.py); raw paths colliding after normalization are rejected. | Current ownership-map evidence: [merged PR #217](https://github.com/1sgtpepper/scieqlint/pull/217) and its later [scanner-ownership synchronization in PR #289](https://github.com/1sgtpepper/scieqlint/pull/289); current import-linter baseline: [merged PR #218](https://github.com/1sgtpepper/scieqlint/pull/218); remaining WorkspaceHost gates: [R1-005B #139](https://github.com/1sgtpepper/scieqlint/issues/139), [R1-009B #146](https://github.com/1sgtpepper/scieqlint/issues/146), [R1-013 #151](https://github.com/1sgtpepper/scieqlint/issues/151), [R1-014 #152](https://github.com/1sgtpepper/scieqlint/issues/152), [R1-015 #153](https://github.com/1sgtpepper/scieqlint/issues/153) |
| 2 | FrontendHost owns source-to-DocumentIR lowering and explicit unknown syntax facts. | [Scanners extract facts and do not parse expressions](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/docs/architecture.md#layer-rules) | Current preview frontends in [`src/scieqlint/frontend/`](https://github.com/1sgtpepper/scieqlint/tree/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/frontend), legacy scanners in [`src/scieqlint/scan/`](https://github.com/1sgtpepper/scieqlint/tree/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/scan), and IR in [`src/scieqlint/ir/model.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/ir/model.py). | Preview coverage in [`tests/test_architecture_contracts.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/tests/test_architecture_contracts.py) and [`tests/test_myst_structure_facts.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/tests/test_myst_structure_facts.py). | Current core-path contract: [merged PR #220](https://github.com/1sgtpepper/scieqlint/pull/220); remaining FrontendHost gates: [R1-025 #162](https://github.com/1sgtpepper/scieqlint/issues/162), [R1-029 #166](https://github.com/1sgtpepper/scieqlint/issues/166), [R1-030 #167](https://github.com/1sgtpepper/scieqlint/issues/167), [R1-031A #168](https://github.com/1sgtpepper/scieqlint/issues/168), [R1-031B #169](https://github.com/1sgtpepper/scieqlint/issues/169), [R1-032A #170](https://github.com/1sgtpepper/scieqlint/issues/170), [R1-032B #171](https://github.com/1sgtpepper/scieqlint/issues/171) |
| 3 | MathHost owns token, AST, MathIR, parser recovery, and unsupported-math representation. | [Parser returns AST or unknown diagnostics](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/docs/architecture.md#layer-rules) | Current parser package [`src/scieqlint/parse/`](https://github.com/1sgtpepper/scieqlint/tree/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/parse); durable MathHost package is planned. | Current parser tests in [`tests/test_parser.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/tests/test_parser.py); durable host gates are planned. | [R1-033 #172](https://github.com/1sgtpepper/scieqlint/issues/172), [R1-034 #173](https://github.com/1sgtpepper/scieqlint/issues/173), [R1-035A #174](https://github.com/1sgtpepper/scieqlint/issues/174), [R1-035B #175](https://github.com/1sgtpepper/scieqlint/issues/175), [R1-036 #176](https://github.com/1sgtpepper/scieqlint/issues/176) |
| 4 | FactHost owns immutable fact records, provenance, snapshot assembly, and snapshot digests. | [Generated-output checks consume explicit provenance facts](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/docs/architecture.md#layer-rules) | Current facts in [`src/scieqlint/facts/`](https://github.com/1sgtpepper/scieqlint/tree/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/facts), including [`src/scieqlint/facts/snapshot.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/facts/snapshot.py). | Preview immutability and projection coverage in [`tests/test_architecture_contracts.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/tests/test_architecture_contracts.py). Digest contract is planned. | [R1-037A #177](https://github.com/1sgtpepper/scieqlint/issues/177), [R1-037B #178](https://github.com/1sgtpepper/scieqlint/issues/178), [R1-038 #179](https://github.com/1sgtpepper/scieqlint/issues/179), [R1-039 #180](https://github.com/1sgtpepper/scieqlint/issues/180), [R1-040 #181](https://github.com/1sgtpepper/scieqlint/issues/181) |
| 5 | QueryHost owns read-only query views and deterministic indexes over `FactSnapshot`. | [Checkers own behavior through stable analysis inputs](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/docs/architecture.md#layer-rules) | Current QueryHost in [`src/scieqlint/query/host.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/query/host.py) and query views in [`src/scieqlint/query/`](https://github.com/1sgtpepper/scieqlint/tree/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/query). | Preview view contracts in [`tests/test_architecture_contracts.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/tests/test_architecture_contracts.py). | [R1-041A #182](https://github.com/1sgtpepper/scieqlint/issues/182), [R1-041B #183](https://github.com/1sgtpepper/scieqlint/issues/183), [R1-042 #184](https://github.com/1sgtpepper/scieqlint/issues/184), [R1-043 #185](https://github.com/1sgtpepper/scieqlint/issues/185) |
| 6 | EngineHost owns deterministic phase barriers, engine descriptors, budgets, and diagnostic IR emission. | [Checkers own algebra, references, dimensions, symbols, and graph behavior](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/docs/architecture.md#layer-rules) | Current preview engines in [`src/scieqlint/engine/`](https://github.com/1sgtpepper/scieqlint/tree/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/engine) plus legacy checkers in [`src/scieqlint/check/`](https://github.com/1sgtpepper/scieqlint/tree/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/check). | Preview engine protocol coverage in [`tests/test_architecture_contracts.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/tests/test_architecture_contracts.py); import boundary gates are planned. | [R1-045 #186](https://github.com/1sgtpepper/scieqlint/issues/186), [R1-046 #187](https://github.com/1sgtpepper/scieqlint/issues/187), [R1-047 #188](https://github.com/1sgtpepper/scieqlint/issues/188), [R1-048 #189](https://github.com/1sgtpepper/scieqlint/issues/189) |
| 7 | PolicyHost owns suppression, baseline, severity, and compatibility policy around diagnostic IR creation and result projection. | [Reporters render diagnostics and do not run checks](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/docs/architecture.md#layer-rules) | A current preview `src/scieqlint/policy/` package owns output-profile support and diagnostic severity selection. Suppression and baseline behavior remains in legacy `src/scieqlint/check/suppressions.py` and `src/scieqlint/diag/baseline.py`; the durable host migration is incomplete. | Preview policy behavior is covered by `tests/test_cross_format_references.py`; legacy behavior remains covered by `tests/test_api.py`, `tests/test_baseline.py`, and `tests/test_cli.py`. Durable PolicyHost gates: [R1-021A #157](https://github.com/1sgtpepper/scieqlint/issues/157), [R1-021B #158](https://github.com/1sgtpepper/scieqlint/issues/158), [R1-022 #159](https://github.com/1sgtpepper/scieqlint/issues/159), [R1-023 #160](https://github.com/1sgtpepper/scieqlint/issues/160), [R1-024 #161](https://github.com/1sgtpepper/scieqlint/issues/161) |
| 8 | SchemaHost owns public projection models, schema versions, serializers, and reporter/export compatibility. | [Graph export models are built from scanner outputs; reporters render diagnostics](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/docs/architecture.md#layer-rules) | Current schemas in [`schemas/`](https://github.com/1sgtpepper/scieqlint/tree/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/schemas), packaged schemas in [`src/scieqlint/schemas/`](https://github.com/1sgtpepper/scieqlint/tree/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/schemas), reporters in [`src/scieqlint/report/`](https://github.com/1sgtpepper/scieqlint/tree/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/report), and graph export in [`src/scieqlint/graph/`](https://github.com/1sgtpepper/scieqlint/tree/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/graph). | Current schema/API readiness checks in [`tests/test_contract_readiness.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/tests/test_contract_readiness.py); durable SchemaHost cutovers are planned. | [R1-049 #190](https://github.com/1sgtpepper/scieqlint/issues/190), [R1-050 #191](https://github.com/1sgtpepper/scieqlint/issues/191), [R1-051 #192](https://github.com/1sgtpepper/scieqlint/issues/192), [R1-052 #193](https://github.com/1sgtpepper/scieqlint/issues/193) |
| 9 | CompatibilityShell temporarily preserves public CLI/API behavior while routing legacy paths to durable hosts. | [CLI owns command-line plumbing only](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/docs/architecture.md#layer-rules) | Current public entry points are [`src/scieqlint/cli.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/cli.py), [`src/scieqlint/api.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/api.py), and [`src/scieqlint/app.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/src/scieqlint/app.py). A `CompatibilityShell` package is not implemented. | Current public compatibility checks in [`tests/test_contract_readiness.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/tests/test_contract_readiness.py). Durable facade and retirement gates are planned. | [R1-053 #194](https://github.com/1sgtpepper/scieqlint/issues/194), [R1-054A #195](https://github.com/1sgtpepper/scieqlint/issues/195), [R1-054B #196](https://github.com/1sgtpepper/scieqlint/issues/196) |

## CompatibilityShell Role

CompatibilityShell is temporary. Its only allowed role is an adapter shell around
public entry points that preserves existing CLI, API, schema, diagnostic, report,
baseline, suppression, and path behavior while delegating durable analysis work
to the hosts above. It must not own analysis semantics, parse raw text for
engines, create a second schema owner, or become a permanent home for legacy
scanner/checker APIs.

The repository currently has public entry points and compatibility tests, but it
does not have a named CompatibilityShell package. The adapter contract and
retirement milestones are planned in [R1-054A #195](https://github.com/1sgtpepper/scieqlint/issues/195)
and [R1-054B #196](https://github.com/1sgtpepper/scieqlint/issues/196).

## Considered Alternatives

Graph-as-database was rejected as the durable core because graph export is a
projection and should not own analysis state or rescan documents.

Reporter-owned schema was rejected because public schemas, compatibility
translators, and deterministic serialization need one SchemaHost owner rather
than per-reporter formats.

Checker-owned parsing was rejected because engines must consume read-only query
views over deterministic facts rather than importing scanner or parser internals.

Permanent compatibility facade was rejected because compatibility adapters are
allowed only to preserve public behavior during migration and must have explicit
retirement issues.

## Consequences

- Architecture conformance is executable only where a linked test, import rule,
  corpus gate, safety gate, or release-gate issue exists. Prose in this ADR is a
  decision record, not conformance evidence by itself.
- Current preview conformance is covered by
  [`tests/test_architecture_contracts.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/tests/test_architecture_contracts.py),
  [`tests/test_contract_readiness.py`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/tests/test_contract_readiness.py),
  and the import-linter contracts in
  [`pyproject.toml`](https://github.com/1sgtpepper/scieqlint/blob/e7dbb1f2cdae2485c4027fc8c415da25c0ef9663/pyproject.toml).
- The completed ownership-map and import-linter baseline gates are recorded by
  [merged PR #217](https://github.com/1sgtpepper/scieqlint/pull/217) and
  [merged PR #218](https://github.com/1sgtpepper/scieqlint/pull/218). Missing executable
  gates remain planned follow-up work, especially raw-text
  parser import checks for engines ([R1-048 #189](https://github.com/1sgtpepper/scieqlint/issues/189)),
  deterministic serialization ([R1-052 #193](https://github.com/1sgtpepper/scieqlint/issues/193)),
  shuffled-input determinism ([R1-059 #200](https://github.com/1sgtpepper/scieqlint/issues/200)),
  no notebook execution ([R1-061 #202](https://github.com/1sgtpepper/scieqlint/issues/202)),
  no network calls ([R1-062 #203](https://github.com/1sgtpepper/scieqlint/issues/203)),
  user-project import bans ([R1-063 #204](https://github.com/1sgtpepper/scieqlint/issues/204)),
  R1 validation ([R1-069 #210](https://github.com/1sgtpepper/scieqlint/issues/210)),
  architecture conformance reporting ([R1-071 #212](https://github.com/1sgtpepper/scieqlint/issues/212)),
  and R1 compatibility audit ([R1-072 #213](https://github.com/1sgtpepper/scieqlint/issues/213)).
- New durable code should move in the ownership order above. Compatibility work
  must state whether a path is current, legacy, temporary, or planned.

## Decision Log

| Date | Status | Entry |
|---|---|---|
| 2026-06-26 | Ratified | R1-001 selects the Deterministic Snapshot Kernel and records durable host ownership order, current-vs-planned repository state, CompatibilityShell limits, and executable gate links. |
