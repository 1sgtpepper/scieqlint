# SciEqLint

SciEqLint catches exact scalar algebra mistakes and broken equation references in a documented subset of scientific documents.

It is intentionally narrow. Unsupported math is reported as unknown or skipped. The checker does not guess.

## First public wedge

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
