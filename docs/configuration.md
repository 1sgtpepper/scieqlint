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

`scanner.inline_math` is opt-in for both path-based checks and the public
`check_documents` API. When it is false, ordinary profiles do not classify explicit
inline-math facts or pass them to query engines. Standalone equation-like text remains
available to `GEN005` under `generated-myst`. The `math-accessibility` profile retains
explicit inline facts while Markdown scanning is enabled so it can report `PORT002`.
Display and structural Markdown analysis remains active.

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
CI instead of being advisory. It is currently the only accepted key under
`[parser]`.

## Project config

```toml
[project]
root = "."
order = ["symbols.md", "chapters/**/*.md"]
```

`project.root` is resolved relative to the config file when a config path is
known, otherwise relative to the current working directory. `project.order`
accepts POSIX-style file or glob patterns relative to `project.root`.

When paths are passed to `scieqlint check` or `scieqlint graph`, `project.order`
controls the analysis order of discovered files. When no paths are passed and
`project.order` is non-empty, both commands discover those ordered project entries.
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


## Validation profile

```toml
[profile]
name = "generated-myst"
source_kind = "jats-xml"
conversion_stage = "xml-to-markdown"
```

The named profile is policy metadata consumed by the normal fact/query/engine
pipeline. Unknown profile names and output targets are rejected rather than
silently running a different rule set.

- `generated-myst` enables source-only formula checks and provenance-backed
  generated-output diagnostics in addition to the ordinary scanner, parser,
  algebra, reference, and structure checks. `source_kind` and `conversion_stage`
  are optional annotations used when an explicit `SourceOrigin` omits those
  fields; they do not identify the source document or prove a producer
  relationship. SciEqLint never reconstructs missing origin metadata.
- `cross-format-references` enables equation-reference portability diagnostics
  and requires `output_profile`. The accepted conservative targets are
  `commonmark`, `myst`, `notebook`, and `typst`. The profile does not run an
  external renderer or claim output parity.
- `math-accessibility` emits diagnostics for explicit inline-math facts that
  lack accessible text metadata. It does not generate alternative text, infer
  metadata from surrounding prose, or apply the policy by default. The profile
  currently lowers Markdown documents only; notebook Markdown cells and LaTeX
  documents are outside its scope.
- `typst-portability` checks a focused set of display-math forms known to be
  unsupported or fragile in Typst publishing paths: `\dfrac`, `\argmin`,
  and `aligned`, `array`, or `matrix` environments combined with TeX
  `\left`/`\right` sizing in Markdown and LaTeX documents. Notebook Markdown
  cells are intentionally outside this profile until their cell-local source
  mapping is part of the structured frontend contract. Active TeX comments are
  ignored while source spans remain source-accurate. It does not invoke Typst
  or translate equations.

The profile table does not enable scanner or parser defaults by itself; those
defaults come from the packaged preset.

For example, to check reference syntax against plain CommonMark:

```toml
[profile]
name = "cross-format-references"
output_profile = "commonmark"
```

The packaged `generated-myst` preset selects that named profile and supplies its
path-based scanner and parser defaults. A hand-written profile table selects policy
metadata only; it does not otherwise change scanner or parser defaults.

The profile consumes caller-owned source mappings when the already-loaded-document
API is used. Attach `SourceOrigin(source_document_id=..., source_kind=...,
conversion_stage=..., preserved_anchor_inventory=...)` to each generated
`SourceDocument`; the checker does not infer that mapping from filenames or
document order. `source_document_id` is the identity-bearing field. Per-document
origin values take precedence over profile annotations, which allows one batch to
carry heterogeneous explicit source identities. Without an origin,
generated-output provenance checks remain quiet for that document. The path-based
CLI does not accept provenance metadata, so `[profile]` alone does not add
provenance diagnostics to a CLI run.

## Presets

Packaged presets are TOML templates loaded before user config. User config values
override preset values.

Available presets:

- `generated-myst`: selects the generated-document profile and enables the
  deterministic Markdown/MyST scanner, inline math, algebra, reference, strict
  parser, and generated-output checks used by generated-document CLI workflows.
  It does not manufacture source provenance.
  Dimension checks stay in `auto` mode and run only when the project adds
  `[vars]`.
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

The preset selects the `generated-myst` profile for path-based checks, so source-only
generated-output diagnostics such as `GEN002` run through this CLI workflow. It
supplies the existing deterministic scanner, parser, algebra, and reference policy,
but does not manufacture source provenance. Use `[profile]` with the already-loaded-
document API when explicit source provenance is available.

## Config schema

The loader validates a fixed schema before document analysis. The currently
accepted tables are `[profile]`, `[project]`, `[baseline]`, `[scanner]`, `[parser]`,
`[checks.algebra]`, `[checks.references]`, `[checks.dimension]`,
`[checks.symbols]`, `[vars]`, `[aliases]`, `[ignore]`, and `[report]`, with the
keys documented on this page. Unknown tables and keys are configuration errors.
`[vars]` and `[aliases]` are dynamic mappings; their entries are validated as
dimension names and aliases rather than as fixed option names.

The severity overrides and resource limits shown in `SPEC.md` are future
specification surface, not accepted settings in the current loader. Use
documented CLI/config toggles such as `--strict-unknowns`,
`[parser].strict_unknowns`, `[checks.references].missing_label_strict`, and
`[checks.dimension].unknown_variables` for current behavior.
