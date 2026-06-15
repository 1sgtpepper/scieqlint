# SciEqLint

SciEqLint checks scientific Markdown, MyST, LaTeX, and notebook documents for
exact scalar algebra mistakes, broken references, and deterministic MyST
structure issues.

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

Generated or MyST-heavy docs can use the packaged profile:

```bash
scieqlint init --preset generated-myst --path scieqlint.generated-myst.toml
scieqlint check "docs/**/*.md" --config scieqlint.generated-myst.toml
```

## Read next

- [Quickstart](quickstart.md)
- [Configuration](configuration.md)
- [Limitations](limitations.md)
- [Diagnostics](diagnostics.md)
- [Contributing](contributing/index.md)
