# Release Checklist

Every release must include:

- release scope statement,
- release check status,
- changelog entry,
- version bump,
- docs update,
- diagnostic catalog update when needed,
- JSON/SARIF schema update when needed,
- accuracy benchmark update when expectations change,
- golden test update when output changes,
- package CI source-distribution test-suite and clean wheel install/CLI smoke gates,
- stable release workflow's separate clean wheel and source-distribution install/CLI smoke gates,
- package-data verification,
- source, wheel, source-distribution, and stable-tag version identity,
- release provenance bound to the protected `main` commit and an immutable stable tag,
- exactly one wheel and one source distribution, with no extra distribution files,
- the generated-formula quality corpus and exact text/JSON goldens executed against
  both installed release artifacts,
- generated-MyST preset initialization, clean and failing CLI checks, and packaged
  JSON schema validation against both installed release artifacts,
- at least 100 independently labeled semantic equations executed through the public
  analysis path with their expected diagnostics and exit status,
- the 100-document/500-equation/500-reference representative workload completing within three seconds,
- release notes with migration notes.

## v1.2.0 product criteria

This release targets Beta maturity for the current static linter: documented
Markdown/MyST, LaTeX and notebook source support; supported scalar algebra and
configured dimensions; references, profiles, baselines and reports. The exact
coverage remains in [limitations](docs/limitations.md) and the [API](docs/api.md).
Generated-source provenance remains caller-supplied.

The [module ownership map](docs/architecture/module-ownership.md) and
[Deterministic Snapshot Kernel ADR](docs/architecture/deterministic-snapshot-kernel-adr.md)
define current, legacy and planned ownership. These product criteria consume
those documents and the existing module/CI boundaries; they introduce no runtime
semantics or new architecture owner.

| Current owner and status | Forbidden behavior or required evidence | Executable gate or deferred follow-up |
|---|---|---|
| `cli`, `api` and `app`: current public entry points and legacy CompatibilityShell orchestration | Direct CLI imports of scanner/parser/checker internals | `lint-imports --config pyproject.toml`; planned AnalysisSession contracts and cutover: [#194](https://github.com/1sgtpepper/scieqlint/issues/194), [#195](https://github.com/1sgtpepper/scieqlint/issues/195), [#196](https://github.com/1sgtpepper/scieqlint/issues/196) |
| `scan`, `frontend` and current `check.algebra`: static source analysis; durable FrontendHost/MathHost cutover remains planned | Notebook/code execution, process/shell calls and user project imports; unsupported math disappearing or losing source/exit semantics | [Security contracts](tests/test_security_contracts.py) and [public unsupported-math contract](tests/test_algebra.py); R1 gates remain [#202](https://github.com/1sgtpepper/scieqlint/issues/202), [#204](https://github.com/1sgtpepper/scieqlint/issues/204), [#201](https://github.com/1sgtpepper/scieqlint/issues/201); parser model/recovery: [#174](https://github.com/1sgtpepper/scieqlint/issues/174), [#175](https://github.com/1sgtpepper/scieqlint/issues/175) |
| `app`/`io`: caller-selected loading; current `WorkspaceHost` normalizes reference paths lexically | A document reference must not authorize another filesystem read. Explicit caller-selected outside-CWD and symlink inputs retain their contracts | Source audit: [reference normalization](src/scieqlint/io/workspace.py), [loading boundary](src/scieqlint/app.py); [path/API tests](tests/test_crossref_path_normalization.py), [caller input tests](tests/test_api.py). Expanded resource policy and negative-fixture gates remain planned in [#152](https://github.com/1sgtpepper/scieqlint/issues/152), [#205](https://github.com/1sgtpepper/scieqlint/issues/205) |
| `facts`, `query`, `engine`, `schema` and `report`: current fact/profile analysis and projections | Diagnostics, schemas, baseline identity or serialized ordering drifting for equivalent inputs | [Golden reports](tests/test_golden_outputs.py), [JSON schemas](tests/test_json_schema.py), [baselines](tests/test_baseline.py), [serialized determinism](tests/test_architecture_contracts.py). Caller/configured symbol order is semantic. Durable manifested gates and schema registry remain [#197](https://github.com/1sgtpepper/scieqlint/issues/197), [#200](https://github.com/1sgtpepper/scieqlint/issues/200), [#190](https://github.com/1sgtpepper/scieqlint/issues/190) |
| Existing [CI](.github/workflows/ci.yml) and [Release](.github/workflows/release.yml) workflows | Missing packaged presets/schemas, inactive clean/failing checks, insufficient independent accuracy evidence or exceeded performance budget | [Installed generated-MyST workflow](tests/test_generated_formula_quality_golden.py), [accuracy corpus](tests/test_accuracy_benchmarks.py), [representative workload](tests/test_stabilization.py); both installed artifacts run the existing release command |

The focused product checks run through ordinary CI:

```bash
python -m pytest -q tests/test_security_contracts.py \
  tests/test_architecture_contracts.py::test_pure_core_layers_execute_through_compatibility_shell_and_kernel \
  tests/test_algebra.py::test_public_unsupported_math_preserves_source_and_exit_contract \
  tests/test_golden_outputs.py tests/test_json_schema.py tests/test_baseline.py \
  tests/test_api.py tests/test_crossref_path_normalization.py
```

The Release workflow runs this command in separate installed wheel and source
distribution environments, with source-tree imports disabled:

```bash
SCIEQLINT_RELEASE_GATE=1 python -m pytest -o pythonpath= -q \
  tests/test_accuracy_benchmarks.py tests/test_generated_formula_quality_golden.py \
  tests/test_stabilization.py
```

After merging the scope to protected `main`, require fresh normal CI and manual
Release validation on that same revision, then apply the publication sequence
below. The architecture conformance report, selected-kernel validation command,
combined kernel fixture and R1 closeout remain in [#210](https://github.com/1sgtpepper/scieqlint/issues/210),
[#211](https://github.com/1sgtpepper/scieqlint/issues/211),
[#212](https://github.com/1sgtpepper/scieqlint/issues/212) and
[#213](https://github.com/1sgtpepper/scieqlint/issues/213). The full release-exit
conformance work in [#209](https://github.com/1sgtpepper/scieqlint/issues/209) remains
part of the [R1 tracker](https://github.com/1sgtpepper/scieqlint/issues/132).

## Release sequence

Before tagging, run `gh workflow run release.yml --ref main` for validation only.
It checks clean wheel and source-distribution installs, version agreement,
accuracy, generated-formula goldens, and the three-second performance budget.
Publication requires a stable tag push and the protected environment approval.

1. Scope lock: update release checks.
2. Data contracts: update models, diagnostics, and schemas first.
3. Core implementation: scanner/parser/checker/reporter changes in separate PRs.
4. Golden fixtures: add good/bad examples and exact output expectations.
5. Docs: update quickstart, limitations, diagnostics, and integration pages.
6. Package CI: build wheel and source distribution, run the source-distribution test suite
   from an extracted tree, and install the wheel in a clean venv for CLI smoke.
7. Release candidate: use a documented prerelease tag such as `v1.1.0rc1` or a prerelease
   branch; the stable release workflow does not consume prerelease tags.
8. Stable tag: after all changes are merged to protected `main`, create an immutable stable
   semver tag at that exact commit. The release workflow rechecks that relationship before
   publication, installs the wheel and source distribution in separate clean venvs, and
   runs CLI and behavioral smoke for each.
9. Trusted publishing: configure the PyPI publisher for `.github/workflows/release.yml`
   and environment `pypi`; require environment approval and disable administrator bypass.
10. Final tag: publish only after release checks pass, the downloaded artifact digest matches,
    the distribution contains exactly one wheel and one source distribution, and no tag or
    protected-branch SHA changed during verification. Release tooling is constrained by
    `.github/release-constraints.txt`, and each run records its resolved dependencies.

A feature is not shipped until docs and fixtures demonstrate it.
