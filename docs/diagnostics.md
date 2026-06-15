# Diagnostics

Diagnostic codes are user-facing API once introduced. The catalog may reserve
codes before every code is emitted by the current analyzer.

## Currently emitted

| Code | Default | Meaning |
|---|---|---|
| `ALG001` | error | Algebraic identity does not hold |
| `PARSE020` | info | Unsupported syntax; check skipped |
| `PARSE021` | info | Unsupported function; check skipped |
| `SCAN001` | warning | Unterminated math container |
| `INP001` | error | File could not be read or decoded |
| `INP002` | warning | Notebook schema issue; scanned best-effort |
| `SCAN010` | warning | Malformed explicit symbol directive |
| `STR001` | warning | ATX heading marker must be followed by a space |
| `STR002` | warning | Fenced block is missing its closing delimiter |
| `STR003` | info | Fenced code block has no language/info string |
| `STR004` | warning | Heading level skips an intermediate parent |
| `STR005` | warning | Document has more than one top-level heading |
| `DIR001` | warning | Malformed MyST directive fence |
| `DIR002` | warning | Malformed MyST directive option |
| `DIR010` | warning | Code-cell directive missing language |
| `DIR011` | warning | Malformed MyST role |
| `DIR012` | warning | Malformed code-cell tags |
| `REF001` | error | Duplicate equation label |
| `REF002` | warning | Missing equation reference target |
| `REF003` | info | Missing equation label in strict mode |
| `REF004` | warning | Missing generic reference target |
| `REF005` | warning | Ambiguous generic reference target |
| `SUP001` | warning | Unknown suppression code |
| `DIM001` | error | Equation sides have different dimensions |
| `DIM002` | error | Addition or subtraction combines incompatible dimensions |
| `DIM010` | warning | Unknown variable dimension |
| `DIM020` | info | Dimension check skipped |
| `SYM001` | warning | Undefined symbol used before explicit definition |

## Generated-output engine

`GEN001` is emitted by the generated-output engine when callers provide
source-to-generated provenance facts. The current CLI/config path does not load
translation provenance.

| Code | Default | Meaning |
|---|---|---|
| `GEN001` | warning | Generated output is missing a preserved source anchor |

## Reserved in catalog

These codes are present in `src/scieqlint/diag/catalog.py` for stable
documentation and reporter metadata, but the current analyzer does not currently
emit them from normal checks:

| Code | Default | Meaning |
|---|---|---|
| `ALG010` | warning | Identity assumes nonzero denominator |
| `ALG020` | info | Algebra check skipped |
| `ALG030` | warning | Algebra check exceeded configured limit |
| `PARSE001` | warning | Could not parse supported-looking math |
| `PARSE022` | info | Unsupported operator; check skipped |
| `SCAN002` | info | Inline math skipped by config |
| `INP003` | warning | File exceeded configured limit |
| `CFG001` | error | Invalid config file |
| `CFG010` | error | Invalid dimension expression |

## Example: ALG001

Input:

```tex
(a+b)^2 = a^2 + b^2
```

Output:

```text
ALG001 algebraic identity does not hold
left - right = 2*a*b
```

## Example: REF002

Input:

```md
See {eq}`missing`.
```

Output:

```text
REF002 equation reference target not found: missing
```

## Example: REF004

Input:

```md
See {ref}`missing`.
```

Output:

```text
REF004 missing generic reference target: missing
```

## Severity controls

The current loader does not implement `[severity]` overrides. Current
severity-affecting controls are exposed through documented CLI/config switches:
`--strict-unknowns` escalates parse-unknown diagnostics, strict missing-label
mode emits `REF003`, and `unknown_variables = "ignore"` suppresses `DIM010` when
dimension checks are active.
