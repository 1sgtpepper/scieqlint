# SciEqLint

SciEqLint checks documented scientific document formats for exact scalar algebra
mistakes and broken equation references.

Unsupported math is reported as unknown or skipped. The checker does not guess.

## Example diagnostics

```md
$$
(a+b)^2 = a^2 + b^2
$$
```

Diagnostic:

```text
ALG001 algebraic identity does not hold
left - right = 2*a*b
```

```md
See {eq}`missing`.
```

Diagnostic:

```text
REF002 equation reference target not found: missing
```

## Read next

- [Quickstart](quickstart.md)
- [Limitations](limitations.md)
- [Diagnostics](diagnostics.md)
- [Contributing](contributing/index.md)
