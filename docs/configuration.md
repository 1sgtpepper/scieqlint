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

## Defaults

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

[checks.dimension]
mode = "auto"
unknown_variables = "warn"

[vars]
# m = "M"
# v = "L T^-1"
# theta = "1"

[ignore]
files = []
```

`ignore.files` accepts POSIX-style glob patterns matched against repository-relative paths
when possible. Use it for generated docs, copied fixtures, or intentional bad examples
that should not affect `scieqlint check .`.

## Dimension config

v0.1.2 introduces the dimension config surface:

```toml
[checks.dimension]
mode = "auto" # "auto", "on", or "off"
unknown_variables = "warn" # "warn" or "ignore"

[vars]
m = "M"
x = "L"
t = "T"
v = "L T^-1"
theta = "1"
```

`auto` runs dimension checks only when `[vars]` is non-empty. Without configured
variables, SciEqLint must stay quiet and emit no unknown-variable dimension
diagnostics. Dimension expressions use the SI base dimensions `M`, `L`, `T`, `I`,
`Theta`, `N`, and `J`; whitespace separates factors, `L^2` sets an integer power,
and `1` means dimensionless.

When dimension checking is active, supported equality sides with different dimensions
emit `DIM001`, supported addition or subtraction with incompatible dimensions emits
`DIM002`, and unknown symbols emit `DIM010` unless `unknown_variables = "ignore"`.

Invalid config fails before document analysis and reports a deterministic error.
