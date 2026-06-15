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

[parser]
strict_unknowns = false

[checks.algebra]
enabled = true

[checks.references]
enabled = true
missing_label_strict = false

[checks.dimension]
mode = "auto"
unknown_variables = "warn"

[checks.symbols]
enabled = false

[baseline]
files = []

[vars]
# m = "M"
# v = "L T^-1"
# theta = "1"

[aliases]
# theta = ["\\theta", "θ"]

[ignore]
files = []

[report]
show_suppressed = false
```

`ignore.files` accepts POSIX-style glob patterns. Discovered files are matched
against both their path relative to `project.root`, when possible, and their
resolved absolute path. Explicitly passed files are still checked even when they
match an ignore pattern.

## Parser strictness

```toml
[parser]
strict_unknowns = true
```

`strict_unknowns` escalates unsupported parser diagnostics such as `PARSE020`,
`PARSE021`, and `PARSE022` from informational diagnostics to errors. Use it for
generated-document gates where unsupported or garbled formula output should fail
CI instead of being advisory. Other `[parser]` keys are reserved placeholders
unless documented here.

## Project config

```toml
[project]
root = "."
order = ["symbols.md", "chapters/**/*.md"]
```

`project.root` is resolved relative to the config file when a config path is
known, otherwise relative to the current working directory. `project.order`
accepts POSIX-style file or glob patterns relative to `project.root`.

When paths are passed to `scieqlint check`, `project.order` controls the
analysis order of discovered files. When no paths are passed and
`project.order` is non-empty, SciEqLint discovers those ordered project entries.
Unmatched files keep deterministic lexical ordering after configured entries.
The default empty order preserves single-command discovery behavior.

`report.show_suppressed` controls text and JSON output. By default, suppressed
diagnostics are hidden from text output, JSON diagnostics, and JSON summary
counts. Set it to `true` to include suppressed diagnostics with their
suppression state and reason. GitHub annotations and SARIF omit suppressed
diagnostics.

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

[aliases]
theta = ["\\theta", "θ"]
```

`auto` runs dimension checks only when `[vars]` is non-empty. Without configured
variables, SciEqLint must stay quiet and emit no unknown-variable dimension
diagnostics. Dimension expressions use the SI base dimensions `M`, `L`, `T`, `I`,
`Theta`, `N`, and `J`; whitespace separates factors, `L^2` sets an integer power,
and `1` means dimensionless.

When dimension checking is active, supported equality sides with different dimensions
emit `DIM001`, supported addition or subtraction with incompatible dimensions emits
`DIM002`, and unknown symbols emit `DIM010` unless `unknown_variables = "ignore"`.
Aliases normalize explicit surface forms before dimension lookup. Alias keys must
name configured `[vars]` entries, and an alias may not collide with another
configured variable or alias.

## Symbol config

```toml
[checks.symbols]
enabled = true
```

When enabled, symbol checks use only explicit `scieqlint-symbol` comments as
definitions and emit `SYM001` for supported math symbols used before definition.
SciEqLint does not infer definitions from prose.

## Baseline config

```toml
[baseline]
files = ["scieqlint-baseline.json"]
```

Baseline files use the same diagnostic fields as JSON output. Relative baseline
file paths resolve from `project.root`. Diagnostics that match by stable
identity are marked `suppressed` with reason `baseline` and do not affect exit
status. New diagnostics that are not present in a baseline remain unsuppressed.
Baselines apply to path-based checks; the already-loaded-document API does not
read baseline files.

Invalid config fails before document analysis and reports a deterministic error.

## Presets

Packaged presets are TOML templates loaded before user config. User config values
override preset values.

Available presets:

- `generated-myst`: validates generated Markdown/MyST scientific output with
  Markdown/MyST math fences, inline math, algebra checks, reference checks, and
  strict parser unknowns enabled. Dimension checks stay in `auto` mode and run
  only when the project adds `[vars]`.
- `mechanics`: enables mechanics dimension checks for common variables such as
  `m`, `a`, `F`, and `E`.

```bash
scieqlint presets list
scieqlint presets show generated-myst
scieqlint presets show mechanics
scieqlint init --preset generated-myst --path scieqlint.generated-myst.toml
scieqlint init --preset mechanics
```

```python
from scieqlint.config.load import load_config

config = load_config("scieqlint.toml", preset="mechanics")
```

For a generated MyST/Markdown CI gate, materialize the preset and run GitHub
annotations with that config:

```bash
scieqlint init --preset generated-myst --path scieqlint.generated-myst.toml
scieqlint check "docs/**/*.md" --config scieqlint.generated-myst.toml --format github
```

## Reserved config surface

The repository-level `scieqlint.toml` may include specification placeholders such
as `[limits]`, `[severity]`, or per-code severity keys. The current loader does
not apply those placeholders. Current severity-affecting behavior is limited to
CLI/config toggles such as `--strict-unknowns`, `[parser].strict_unknowns`,
`[checks.references].missing_label_strict`, and
`[checks.dimension].unknown_variables`.
