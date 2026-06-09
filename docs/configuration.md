# Configuration

Default config path:

```text
scieqlint.toml
```

Search order:

1. explicit `--config` path,
2. current working directory,
3. parent directories until no more parents remain,
4. built-in defaults.

SciEqLint does not currently stop discovery at a VCS root. Run from the intended
project directory, or pass `--config`, when parent directories may also contain a
`scieqlint.toml`.

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

[checks.references]
enabled = true
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

[report]
show_suppressed = false
```

`ignore.files` accepts POSIX-style glob patterns. Discovered files are matched
against both their path relative to the current working directory, when possible,
and their resolved absolute path. Explicitly passed files are still checked even
when they match an ignore pattern.

`report.show_suppressed` controls JSON output only. By default, suppressed
diagnostics are hidden from JSON diagnostics and summary counts. Set it to
`true` to include suppressed diagnostics with their suppression state and reason.

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

## Presets

Packaged presets are TOML templates loaded before user config. User config values
override preset values. The initial preset is `mechanics`.

```bash
scieqlint presets list
scieqlint presets show mechanics
scieqlint init --preset mechanics
```

```python
from scieqlint.config.load import load_config

config = load_config("scieqlint.toml", preset="mechanics")
```

## Reserved config surface

The repository-level `scieqlint.toml` may include specification placeholders such
as `[project]`, `[parser]`, `[limits]`, `[report]`, `[severity]`, or per-code
severity keys. The v0.1.5 loader does not apply those placeholders. Current
severity-affecting behavior is limited to CLI/config toggles such as
`--strict-unknowns`, `[checks.references].missing_label_strict`, and
`[checks.dimension].unknown_variables`.
