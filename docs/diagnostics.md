# Diagnostics

Diagnostic codes are user-facing API once introduced.

## v0.1.0 catalog

| Code | Default | Meaning |
|---|---|---|
| `ALG001` | error | Algebraic identity does not hold |
| `ALG010` | warning | Identity assumes nonzero denominator |
| `ALG020` | info | Algebra check skipped |
| `ALG030` | warning | Algebra check exceeded configured limit |
| `PARSE001` | warning | Could not parse supported-looking math |
| `PARSE020` | info | Unsupported syntax; check skipped |
| `PARSE021` | info | Unsupported function; check skipped |
| `PARSE022` | info | Unsupported operator; check skipped |
| `SCAN001` | warning | Unterminated math container |
| `SCAN002` | info | Inline math skipped by config |
| `INP001` | error | File could not be read or decoded |
| `INP003` | warning | File exceeded configured limit |
| `CFG001` | error | Invalid config file |
| `REF001` | error | Duplicate equation label |
| `REF002` | warning | Missing equation reference target |
| `REF003` | info | Missing equation label in strict mode |

## v0.1.2 catalog

| Code | Default | Meaning |
|---|---|---|
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

## Severity overrides

```toml
[severity]
DIM010 = "info"
PARSE020 = "ignore"
```

Valid values are `error`, `warning`, `info`, and `ignore`.
