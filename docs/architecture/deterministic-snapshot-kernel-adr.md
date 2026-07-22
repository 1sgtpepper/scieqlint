# ADR R1-001: Deterministic Snapshot Kernel

Status: Ratified for R1 architecture governance
Decision date: 2026-06-26
Owner: Architecture governance
Issue: [R1-001 / GitHub #133](https://github.com/Kuhai9801/scieqlint/issues/133)

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

## Scope

This decision record accepts only architecture documents, the module graph, and
CI/import configuration as inputs. Its required output is this reviewed ADR and
architecture decision log artifact. It does not change runtime code, CLI/API
signatures, diagnostics, schemas, ordering behavior, discovery, baselines, or
suppressions.

The kernel's total ordering key is:

```text
KernelOrderKey = (canonical_uri, source_start, source_end, owner_phase, stable_id)
```

Durable implementations must use this key, or a stricter documented projection of
it, whenever equivalent inputs can arrive in shuffled order. Shuffled equivalent
inputs must produce byte-identical machine output after advisory fields explicitly
declared as non-stable are removed.

## Selected Architecture

The normative summary remains [Architecture: Layer rules](../architecture.md#layer-rules).
This ADR ratifies the durable ownership order below and records which parts are
current, legacy, or planned.

| Order | Durable owner and value | Normative summary | Current repository package | Contract or executable evidence | Release gate or follow-up |
|---|---|---|---|---|---|
| 1 | WorkspaceHost owns workspace discovery, canonical paths, and source loading. | [CLI owns plumbing; scanners do not read files](../architecture.md#layer-rules) | Current legacy loading in [`src/scieqlint/io/`](https://github.com/Kuhai9801/scieqlint/tree/main/src/scieqlint/io); planned WorkspaceHost package is not present. | Existing source/document tests in [`tests/test_source.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_source.py); broader boundary is planned. | [R1-002A #134](https://github.com/Kuhai9801/scieqlint/issues/134), [R1-002B #135](https://github.com/Kuhai9801/scieqlint/issues/135), [R1-063 #204](https://github.com/Kuhai9801/scieqlint/issues/204) |
| 2 | FrontendHost owns source-to-DocumentIR lowering and explicit unknown syntax facts. | [Scanners extract facts and do not parse expressions](../architecture.md#layer-rules) | Current preview frontends in [`src/scieqlint/frontend/`](https://github.com/Kuhai9801/scieqlint/tree/main/src/scieqlint/frontend), legacy scanners in [`src/scieqlint/scan/`](https://github.com/Kuhai9801/scieqlint/tree/main/src/scieqlint/scan), and IR in [`src/scieqlint/ir/model.py`](https://github.com/Kuhai9801/scieqlint/blob/main/src/scieqlint/ir/model.py). | Preview coverage in [`tests/test_architecture_contracts.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_architecture_contracts.py) and [`tests/test_myst_structure_facts.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_myst_structure_facts.py). | [R1-004 #137](https://github.com/Kuhai9801/scieqlint/issues/137), [R1-048 #189](https://github.com/Kuhai9801/scieqlint/issues/189) |
| 3 | MathHost owns token, AST, MathIR, parser recovery, and unsupported-math representation. | [Parser returns AST or unknown diagnostics](../architecture.md#layer-rules) | Current parser package [`src/scieqlint/parse/`](https://github.com/Kuhai9801/scieqlint/tree/main/src/scieqlint/parse); durable MathHost package is planned. | Current parser tests in [`tests/test_parser.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_parser.py); durable host gates are planned. | [R1-035A #174](https://github.com/Kuhai9801/scieqlint/issues/174), [R1-035B #175](https://github.com/Kuhai9801/scieqlint/issues/175) |
| 4 | FactHost owns immutable fact records, provenance, snapshot assembly, and snapshot digests. | [Generated-output checks consume explicit provenance facts](../architecture.md#layer-rules) | Current facts in [`src/scieqlint/facts/`](https://github.com/Kuhai9801/scieqlint/tree/main/src/scieqlint/facts), including [`src/scieqlint/facts/snapshot.py`](https://github.com/Kuhai9801/scieqlint/blob/main/src/scieqlint/facts/snapshot.py). | Preview immutability and projection coverage in [`tests/test_architecture_contracts.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_architecture_contracts.py). Digest contract is planned. | [R1-037A #177](https://github.com/Kuhai9801/scieqlint/issues/177), [R1-037B #178](https://github.com/Kuhai9801/scieqlint/issues/178), [R1-040 #181](https://github.com/Kuhai9801/scieqlint/issues/181), [R2-130 #315](https://github.com/Kuhai9801/scieqlint/issues/315) |
| 5 | QueryHost owns read-only query views and deterministic indexes over `FactSnapshot`. | [Checkers own behavior through stable analysis inputs](../architecture.md#layer-rules) | Current QueryHost in [`src/scieqlint/query/host.py`](https://github.com/Kuhai9801/scieqlint/blob/main/src/scieqlint/query/host.py) and query views in [`src/scieqlint/query/`](https://github.com/Kuhai9801/scieqlint/tree/main/src/scieqlint/query). | Preview view contracts in [`tests/test_architecture_contracts.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_architecture_contracts.py). | [R1-041A #182](https://github.com/Kuhai9801/scieqlint/issues/182), [R1-041B #183](https://github.com/Kuhai9801/scieqlint/issues/183), [R2-094C #258](https://github.com/Kuhai9801/scieqlint/issues/258) |
| 6 | EngineHost owns deterministic phase barriers, engine descriptors, budgets, and diagnostic IR emission. | [Checkers own algebra, references, dimensions, symbols, and graph behavior](../architecture.md#layer-rules) | Current preview engines in [`src/scieqlint/engine/`](https://github.com/Kuhai9801/scieqlint/tree/main/src/scieqlint/engine) plus legacy checkers in [`src/scieqlint/check/`](https://github.com/Kuhai9801/scieqlint/tree/main/src/scieqlint/check). | Preview engine protocol coverage in [`tests/test_architecture_contracts.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_architecture_contracts.py); import boundary gates are planned. | [R1-045 #186](https://github.com/Kuhai9801/scieqlint/issues/186), [R1-046 #187](https://github.com/Kuhai9801/scieqlint/issues/187), [R1-048 #189](https://github.com/Kuhai9801/scieqlint/issues/189), [R2-132 #317](https://github.com/Kuhai9801/scieqlint/issues/317) |
| 7 | PolicyHost owns suppression, baseline, severity, and compatibility policy after diagnostic IR creation. | [Reporters render diagnostics and do not run checks](../architecture.md#layer-rules) | Current policy-like code is legacy and split across [`src/scieqlint/check/suppressions.py`](https://github.com/Kuhai9801/scieqlint/blob/main/src/scieqlint/check/suppressions.py) and [`src/scieqlint/diag/baseline.py`](https://github.com/Kuhai9801/scieqlint/blob/main/src/scieqlint/diag/baseline.py); durable PolicyHost package is planned. | Current behavior is covered by [`tests/test_api.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_api.py), [`tests/test_baseline.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_baseline.py), and [`tests/test_cli.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_cli.py); durable post-IR policy gates are planned. | [R2-117A #294](https://github.com/Kuhai9801/scieqlint/issues/294), [R2-118A #296](https://github.com/Kuhai9801/scieqlint/issues/296), [R2-120 #299](https://github.com/Kuhai9801/scieqlint/issues/299) |
| 8 | SchemaHost owns public projection models, schema versions, serializers, and reporter/export compatibility. | [Graph export models are built from scanner outputs; reporters render diagnostics](../architecture.md#layer-rules) | Current schemas in [`schemas/`](https://github.com/Kuhai9801/scieqlint/tree/main/schemas), packaged schemas in [`src/scieqlint/schemas/`](https://github.com/Kuhai9801/scieqlint/tree/main/src/scieqlint/schemas), reporters in [`src/scieqlint/report/`](https://github.com/Kuhai9801/scieqlint/tree/main/src/scieqlint/report), and graph export in [`src/scieqlint/graph/`](https://github.com/Kuhai9801/scieqlint/tree/main/src/scieqlint/graph). | Current schema/API readiness checks in [`tests/test_contract_readiness.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_contract_readiness.py); durable SchemaHost cutovers are planned. | [R1-049 #190](https://github.com/Kuhai9801/scieqlint/issues/190), [R1-050 #191](https://github.com/Kuhai9801/scieqlint/issues/191), [R2-121A #300](https://github.com/Kuhai9801/scieqlint/issues/300), [R2-125A #305](https://github.com/Kuhai9801/scieqlint/issues/305), [R2-126A #307](https://github.com/Kuhai9801/scieqlint/issues/307), [R2-127A #309](https://github.com/Kuhai9801/scieqlint/issues/309), [R2-128A #311](https://github.com/Kuhai9801/scieqlint/issues/311) |
| 9 | CompatibilityShell temporarily preserves public CLI/API behavior while routing legacy paths to durable hosts. | [CLI owns command-line plumbing only](../architecture.md#layer-rules) | Current public entry points are [`src/scieqlint/cli.py`](https://github.com/Kuhai9801/scieqlint/blob/main/src/scieqlint/cli.py), [`src/scieqlint/api.py`](https://github.com/Kuhai9801/scieqlint/blob/main/src/scieqlint/api.py), and [`src/scieqlint/app.py`](https://github.com/Kuhai9801/scieqlint/blob/main/src/scieqlint/app.py). A `CompatibilityShell` package is not implemented. | Current public compatibility checks in [`tests/test_contract_readiness.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_contract_readiness.py). Durable facade and retirement gates are planned. | [R1-053 #194](https://github.com/Kuhai9801/scieqlint/issues/194), [R1-054A #195](https://github.com/Kuhai9801/scieqlint/issues/195), [R1-054B #196](https://github.com/Kuhai9801/scieqlint/issues/196), [R2-133A #318](https://github.com/Kuhai9801/scieqlint/issues/318), [R2-133B #319](https://github.com/Kuhai9801/scieqlint/issues/319), [R3-193 #391](https://github.com/Kuhai9801/scieqlint/issues/391), [R3-196 #395](https://github.com/Kuhai9801/scieqlint/issues/395) |

## CompatibilityShell Role

CompatibilityShell is temporary. Its only allowed role is an adapter shell around
public entry points that preserves existing CLI, API, schema, diagnostic, report,
baseline, suppression, and path behavior while delegating durable analysis work
to the hosts above. It must not own analysis semantics, parse raw text for
engines, create a second schema owner, or become a permanent home for legacy
scanner/checker APIs.

The repository currently has public entry points and compatibility tests, but it
does not have a named CompatibilityShell package. The adapter contract and
retirement milestones are planned in [R1-054A #195](https://github.com/Kuhai9801/scieqlint/issues/195),
[R1-054B #196](https://github.com/Kuhai9801/scieqlint/issues/196),
[R2-133A #318](https://github.com/Kuhai9801/scieqlint/issues/318),
[R2-133B #319](https://github.com/Kuhai9801/scieqlint/issues/319),
[R3-193 #391](https://github.com/Kuhai9801/scieqlint/issues/391), and
[R3-196 #395](https://github.com/Kuhai9801/scieqlint/issues/395).

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
  [`tests/test_architecture_contracts.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_architecture_contracts.py),
  [`tests/test_contract_readiness.py`](https://github.com/Kuhai9801/scieqlint/blob/main/tests/test_contract_readiness.py),
  and the import-linter contracts in
  [`pyproject.toml`](https://github.com/Kuhai9801/scieqlint/blob/main/pyproject.toml).
- Missing executable gates remain planned follow-up work, especially package
  ownership and import-linter hardening ([R1-002A #134](https://github.com/Kuhai9801/scieqlint/issues/134),
  [R1-002B #135](https://github.com/Kuhai9801/scieqlint/issues/135)), raw-text
  parser import checks for engines ([R1-048 #189](https://github.com/Kuhai9801/scieqlint/issues/189)),
  deterministic serialization ([R1-052 #193](https://github.com/Kuhai9801/scieqlint/issues/193)),
  shuffled-input determinism ([R1-059 #200](https://github.com/Kuhai9801/scieqlint/issues/200)),
  no notebook execution ([R1-061 #202](https://github.com/Kuhai9801/scieqlint/issues/202)),
  no network calls ([R1-062 #203](https://github.com/Kuhai9801/scieqlint/issues/203)),
  user-project import bans ([R1-063 #204](https://github.com/Kuhai9801/scieqlint/issues/204)),
  R1 validation ([R1-069 #210](https://github.com/Kuhai9801/scieqlint/issues/210)),
  architecture conformance reporting ([R1-071 #212](https://github.com/Kuhai9801/scieqlint/issues/212)),
  and R1 compatibility audit ([R1-072 #213](https://github.com/Kuhai9801/scieqlint/issues/213)).
- New durable code should move in the ownership order above. Compatibility work
  must state whether a path is current, legacy, temporary, or planned.

## Decision Log

| Date | Status | Entry |
|---|---|---|
| 2026-06-26 | Ratified | R1-001 selects the Deterministic Snapshot Kernel and records durable host ownership order, current-vs-planned repository state, CompatibilityShell limits, and executable gate links. |
