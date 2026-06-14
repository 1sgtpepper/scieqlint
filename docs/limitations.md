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

## Generated output and model quality

The architecture-preview `generated` profile validates deterministic document
facts in generated Markdown/MyST output. It can report malformed supported
structure, generic and equation reference failures, math-container issues, generated
references that remain unresolved, and source MyST anchors missing from a paired
generated document.

The profile does not judge translation quality, prose quality, OCR confidence,
model hallucination, image-to-math fidelity, or semantic equivalence of formulas
whose structure is outside SciEqLint's supported facts. Those checks require a
human, renderer, OCR-specific validator, or model-quality review. SciEqLint's
generated-output checks are deterministic gates over the text and explicit
source/generated pairs supplied to the architecture-preview API.

## Notebooks

Notebooks are never executed. v0.1.4 scans Markdown cells, preserves notebook
cell metadata in diagnostics, ignores code cells, and emits deterministic `INP001`
or `INP002` input diagnostics for malformed notebook inputs. Code-cell variable
analysis, notebook execution, and full Jupyter schema validation are deferred.
