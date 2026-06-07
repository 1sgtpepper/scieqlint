# Configuration

Default config path:

```text
scieqlint.toml
```

Search order:

1. explicit `--config` path,
2. current working directory,
3. parent directories until repo root,
4. built-in defaults.

## v0.1.0 defaults

```toml
[project]
root = "."
order = []

[scanner]
markdown = true
inline_math = false
math_fences = true

[checks.algebra]
enabled = true
unknown = "info"
denominator_warnings = true

[checks.references]
enabled = true
missing = "warn"
duplicate_labels = "error"
missing_label_strict = false
```

Invalid config exits 2 and should report all detected errors where practical.
