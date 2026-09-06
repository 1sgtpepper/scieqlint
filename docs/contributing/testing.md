# Testing

Tests protect documented behavior, not just code coverage.

## Test types

- Unit tests for data contracts and pure logic.
- Scanner tests for extraction and spans.
- Parser tests for supported and unsupported syntax.
- Checker tests for exact behavior.
- Golden tests for text, JSON, GitHub, and SARIF outputs.
- Package-resource tests for installed wheels.
- Pre-commit integration tests build a temporary hook repository from the source
  under test, so they do not depend on the checkout's Git revision.
- Source distributions include the inputs required by the shipped test suite. CI runs
  that suite from an extracted archive; the repository-only pack-manifest inventory
  check is skipped when Git metadata is unavailable.

## Public bug regressions

Keep regressions beside the component that owns the behavior and exercise the public
in-memory analysis path. Assert the complete ordered diagnostic semantics, relevant
result counts, and source spans derived independently from the input. A clean regression
must include a nearby active control that would fail if the scanner, parser, or checker
were disabled. Use pytest node or parameter IDs as the runnable case identity.

Mark only a newly added test that reproduces a public bug with
`@pytest.mark.public_regression`. Do not mark active controls, normative contract tests,
or existing tests being strengthened. Pull-request CI runs each new marked node against
the head and base package sources. The node is accepted only when head passes and base
fails by an assertion that pytest attributes to the proposed `tests/` tree. Direct test
assertions, private test helpers, and `pytest.fail()` are valid oracles; an assertion from
the package or a dependency is an API incompatibility unless the test catches it and
asserts the intended behavior explicitly. Setup and teardown must both pass normally:
failures, skips, and expected-failure outcomes in either phase are incompatible. A base
pass or API incompatibility is rejected and reported with the exact node ID.

To replay against an existing base checkout directly:

```bash
python tools/public_regression_replay.py --base ../scieqlint-base
```

## Accuracy corpus

`benchmarks/accuracy/corpus-v1.json` is strict versioned JSON. Every case has a
positive or negative label, one target rule, source format, scientific domain,
provenance, and license or synthetic status. A non-synthetic case must also carry
an `independent_equation_id` and contain exactly one equality-bearing line under the
checkers' equation semantics. Its identity preserves checker token boundaries and
unrecognized non-whitespace text while normalizing checker-equivalent grouping braces
and lexically insignificant spacing. Scanner-owned LaTeX alignment markers, paths,
source format, notebook source segmentation, and inert notebook metadata do not change
that identity; literal Markdown ampersands and identifier boundaries do. Equivalent
identities must reuse one ID, and repeated IDs must keep the same equation and label/rule
metadata. Non-equation display math, multiple-equation wrappers, format wrappers, and
synthetic fixtures cannot inflate the stable accuracy threshold.
Expected diagnostics require independent mathematical evidence or documented
behavior. Execute cases through `scieqlint.api.check_documents`; do not derive
expectations from the implementation under test. Profile-specific cases record the
source provenance, conversion settings,
output target, and project policy needed to reproduce their public behavior. Unknown,
missing, and duplicate fields are errors. The checked-in corpus contains 169
fixtures: 102 source equations with independently justified expectations (39 positive
and 63 negative) and 67 synthetic cases. The 100-equation accuracy gate runs in ordinary PR CI as
well as release validation. Canary comparisons and precision/recall release gates
remain out of scope until corpus diversity and baseline variance have been assessed.

The [source review packet](https://github.com/1sgtpepper/scieqlint/blob/main/benchmarks/accuracy/source-review-v1.md)
records original expressions, source hashes and locations, notation changes,
assumptions, dimensional declarations and independent algebraic counterexamples
for the 100 additional cases. Keep proposals without independent evidence outside
the release corpus; passing CI alone does not establish correct expectations.
Preserve source and family identities when adding cases, and update the count and
review evidence together.

An algebraic non-identity from a textbook exercise is not necessarily an error in
that exercise. Dimensional homogeneity does not prove a physical law, and an
unsupported-syntax diagnostic does not establish mathematical truth. The supplied
Markdown and notebook wrappers exercise input formats; their equations originated
in TeX and must not be presented as naturally occurring documents in those formats.

## Bounded property checks

The pull-request suite includes at most three deterministic Hypothesis properties for
semantic invariants that benefit from nearby generated forms. Keep each property bounded,
set `derandomize=True`, disable the example database, and do not suppress health checks.
When a property exposes a production defect, first reduce the example to an owner-local
regression test; the production fix must make that fixed reproducer pass. Scheduled deep
profiles, fuzzers, and mutation workflows remain separate work.

## Local loop

```bash
pytest
pytest --cov=scieqlint --cov-report=term-missing
ruff format --check .
ruff check .
pyright
```

A diagnostic behavior change without tests and docs is not complete.
