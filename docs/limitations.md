# Limitations

This page records the file formats, math grammar, scanners, and integrations
implemented in the current release.

## Current supported source files

| Format | Status |
|---|---|
| `.md` | supported |
| `.markdown` | supported |
| `.tex` | supported for v0.1.3 LaTeX containers |
| `.ipynb` | supported for v0.1.4 Markdown cells |

## Core supported math forms

```md
$$
(a+b)^2 = a^2 + b^2
$$
```

````md
```math
E = mc^2
```
````

````md
```{math}
:label: energy
E = mc^2
```
````

## Core grammar subset

| Construct | Status |
|---|---|
| rational numbers | supported |
| symbols | supported |
| `+`, `-`, `*`, `/` | supported |
| implicit multiplication | supported within documented parser rules |
| integer powers | supported |
| `\frac{a}{b}` | supported |
| `\sqrt{x}` | supported when exact handling is possible |
| trig/log/exp | deferred |
| integrals/derivatives/limits | deferred |
| matrices/vectors/tensors | deferred |
| non-integer powers except `sqrt` | deferred |
| user TeX macros | deferred |

Unsupported syntax must produce an unknown/skipped diagnostic, not a crash and not a guessed answer.

## Current integration outputs

- text
- json
- github
- sarif

`scieqlint graph` exports deterministic JSON graph data for supported equation
labels and references.

## Reference checks

SciEqLint checks supported equation references and Markdown links to supported
equation labels. Explicit MyST heading anchors written as `(label)=` immediately
before a heading are treated as document-structure targets, so Markdown links such
as `[](#label)` and `[#label](#label)` do not emit equation-reference
diagnostics when that target exists. Orphaned `(label)=` lines are not treated as
valid targets. MyST `{ref}` roles to missing or ambiguous generic targets use
generic-reference diagnostics instead of equation-reference diagnostics. This
also catches generated output that drops a heading anchor while preserving a
later `{ref}` to that anchor.

## MyST structure linting

The architecture frontend lowers MyST headings, target anchors, fenced blocks,
directives, generic roles, equation roles, and code-cell facts. The structure
engine emits deterministic diagnostics for malformed ATX headings, unclosed
non-math fences, skipped heading levels, repeated top-level headings, generic
fences without an info string, malformed MyST directive openers,
malformed MyST directive options, malformed `{ref}`/`{eq}`/`{numref}` role
syntax, missing code-cell language arguments, and malformed code-cell tag lists.

This is a conservative lint subset, not a full MyST parser. Unknown custom
directive names remain allowed. Valid MyST target anchors such as `(label)=`
before headings are treated as anchors, not headings or malformed prose.

## Suppression comments

SciEqLint supports narrow source suppressions for Markdown and LaTeX:

```md
<!-- scieqlint-disable-next-line ALG001 -->
```

```tex
% scieqlint-disable-current-block ALG001
```

Suppressed diagnostics do not affect the CLI exit code. They are hidden from
text and JSON output by default, can be included in text and JSON with
`report.show_suppressed = true`, and are omitted from GitHub annotation and
SARIF output. Unknown suppression codes emit `SUP001`.

Diagnostic baselines mark matching diagnostics as suppressed for path-based
checks. Baselines are deterministic JSON files that use the same diagnostic
identity fields as JSON output; they do not apply to `check_documents()`.

## v0.1.3 LaTeX source subset

SciEqLint scans supported LaTeX display containers in `.tex` files:

- `\[ ... \]`
- `$$ ... $$`
- `equation` and `equation*`
- `align` and `align*`

For `align`, rows are split on unescaped `\\` and alignment markers are removed before
equation checks run. SciEqLint extracts `\label{...}`, `\ref{...}`, and `\eqref{...}`
for reference checks. LaTeX macro expansion and full environment parsing are deferred.

## Dimensions

Dimensions are quiet without config. v0.1.2 adds configured dimension checking;
zero-config mode must not emit unknown-variable dimension noise. The `mechanics`
preset provides packaged dimension defaults, and `[aliases]` can normalize
explicit symbol spellings before dimension lookup. Presets are TOML templates,
not a unit database, and aliases must be listed explicitly.

## Symbols

Explicit Markdown and LaTeX `scieqlint-symbol` comments can define symbols for
the opt-in undefined-symbol check. SciEqLint does not infer symbols from prose.

## Notebooks

Notebooks are never executed. v0.1.4 scans Markdown cells, preserves notebook
cell metadata in diagnostics, ignores code cells, and emits deterministic `INP001`
or `INP002` input diagnostics for malformed notebook inputs. Code-cell variable
analysis, notebook execution, and full Jupyter schema validation are deferred.
