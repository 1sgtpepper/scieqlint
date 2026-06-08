# Good First Issues

These are seed issues for opening the repository. Each issue is intended to stay
small and reviewable.

## 1. CLI smoke tests for v0.0.1

## Summary

Add smoke coverage for the first CLI commands.

## Affected Area

```text
Release: v0.0.1
Area: CLI
```

## Change

Cover `scieqlint --help`, `scieqlint demo`, and `python -m scieqlint --help`.

## Test Notes

Use the repository's CLI test style.

## 2. LineIndex tests

## Summary

Add source-location tests for one-based line and column mapping.

## Affected Area

```text
Release: v0.1.0
Area: IO
```

## Change

Cover mixed short lines and a final line without a trailing newline.

## Test Notes

Keep the expected locations explicit.

## 3. Diagnostic catalog table

## Summary

Keep diagnostic catalog entries and documentation aligned.

## Affected Area

```text
Release: v0.1.0
Area: diagnostics/docs
```

## Change

Add or update coverage that catches catalog/docs drift.

## Test Notes

Use independent expected diagnostic metadata.

## 4. Markdown display math fixture extraction

## Summary

Cover Markdown display math block extraction.

## Affected Area

```text
Release: v0.1.0
Area: scanner
```

## Change

Cover `$$ ... $$` blocks, stable line/column spans, and unterminated containers
that warn instead of crashing.

## Test Notes

Use small Markdown fixtures.

## 5. MyST directive label extraction

## Summary

Cover MyST math labels and references.

## Affected Area

```text
Release: v0.1.0
Area: scanner
```

## Change

Cover math directive labels, `{eq}` references, simple `{numref}` references, raw
reference text, and deterministic source spans.

## Test Notes

Use focused MyST examples.

## 6. Parser unsupported-function regression tests

## Summary

Add regression coverage for unsupported functions.

## Affected Area

```text
Release: v0.1.0
Area: parser
```

## Change

Show unsupported functions such as `\sin(x)`, `\cos(x)`, `\log(x)`, and `\exp(x)`
produce the expected parser diagnostic without raising an exception.

## Test Notes

Check that unsupported functions do not emit algebra diagnostics.

## 7. Algebra famous-bad fixture

## Summary

Lock the README algebra demo with a fixture.

## Affected Area

```text
Release: v0.1.0
Area: checker
```

## Change

Add the `(a+b)^2 = a^2 + b^2` fixture and stable text output showing the algebra
diagnostic detail.

## Test Notes

Keep golden output stable across operating systems.

## 8. JSON schema validation test

## Summary

Validate deterministic JSON output against the checked-in schema.

## Affected Area

```text
Release: v0.1.0
Area: reporter/schema
```

## Change

Validate golden JSON against the schema and keep deterministic output fields stable.

## Test Notes

Use a checked-in golden file.

## 9. Limitations page first pass

## Summary

Document the supported SciEqLint subset.

## Affected Area

```text
Release: v0.1.0
Area: docs
```

## Change

Document supported grammar, supported label/reference forms, unsupported examples,
and how unknown math is reported.

## Test Notes

Keep examples consistent with the implemented parser behavior.

## 10. Package-resource smoke test

## Summary

Cover package resources in an installed wheel.

## Affected Area

```text
Release: v0.0.1/v0.1.0
Area: packaging
```

## Change

Cover package resource loading, wheel contents for schemas and grammar, and a clean
install smoke check for `scieqlint --help`.

## Test Notes

Use repository-native packaging checks.
