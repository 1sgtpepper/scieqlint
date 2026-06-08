# Limitations

Limitations are part of SciEqLint's trust model.

SciEqLint checks a supported subset. It is not a theorem prover, a full CAS, a LaTeX compiler, a Sphinx/Jupyter Book build validator, or a notebook execution system.

## v0.1.0 supported source files

| Format | Status |
|---|---|
| `.md` | supported |
| `.markdown` | supported |
| `.tex` | supported for v0.1.3 LaTeX containers |
| `.ipynb` | v0.1.4 |

## v0.1.0 supported math forms

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

## v0.1.0 grammar subset

| Construct | Status |
|---|---|
| rational numbers | supported |
| symbols | supported |
| `+`, `-`, `*`, `/` | supported |
| implicit multiplication | supported within documented parser rules |
| integer powers | supported |
| `\frac{a}{b}` | supported |
| `\sqrt{x}` | supported when exact handling is possible |
| trig/log/exp | unsupported until later optional scope |
| integrals/derivatives/limits | unsupported |
| matrices/vectors/tensors | unsupported |
| non-integer powers except `sqrt` | unsupported |
| user TeX macros | unsupported |

Unsupported syntax must produce an unknown/skipped diagnostic, not a crash and not a guessed answer.

## v0.1.3 LaTeX source subset

SciEqLint scans supported LaTeX display containers in `.tex` files:

- `\[ ... \]`
- `$$ ... $$`
- `equation` and `equation*`
- `align` and `align*`

For `align`, rows are split on unescaped `\\` and alignment markers are removed before
equation checks run. LaTeX macro expansion and full environment parsing are out of scope.

## Why unknown is good

A small exact checker that says “unknown” honestly is better than a broad checker that guesses. Unknown means SciEqLint did not prove the equation false within the supported subset.

## Dimensions

Dimensions are quiet without config. v0.1.2 adds configured dimension checking; zero-config mode must not emit unknown-variable dimension noise.

## Notebooks

Notebooks are never executed. v0.1.4 scans Markdown cells only.
