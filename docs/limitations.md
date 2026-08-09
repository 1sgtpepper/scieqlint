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

Dollar math follows a conservative SciEqLint profile derived from the referenced
`mdit-py-plugins` behavior: escaped dollars and borrowed `$$$` delimiters remain
prose; display `$$` starts after zero to three leading ASCII spaces at the start
of a line and closes only at the end of a source line (optionally followed by one
complete label suffix); single-dollar inline math may be adjacent to ordinary
text but stays on one source line. Empty bodies and unmatched delimiters are not
facts.

## Core grammar subset

| Construct | Status |
|---|---|
| rational numbers | supported |
| symbols | supported |
| `+`, `-`, `*`, `/` | supported |
| implicit multiplication | supported within documented parser rules |
| integer powers | supported for exponents from `-1000` through `1000` |
| `\frac{a}{b}` | supported |
| `\sqrt{n}` | supported for numeric perfect-square rational operands only |
| trig/log/exp | deferred |
| integrals/derivatives/limits | deferred |
| matrices/vectors/tensors | deferred |
| non-integer powers and symbolic square roots | deferred |
| user TeX macros | deferred |

Configured dimension aliases match complete surface tokens and do not split a
longer identifier. This boundary also applies when an alias ends in punctuation,
so `v.` does not match the prefix of `v.foo`; numeric coefficients may be
adjacent to aliases as implicit multiplication.
Each non-empty line-separated equation in a math container is checked
independently; line breaks do not create chained equalities. A line ending in
`=` is treated as an incomplete equation rather than continued on the next line.

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

Strict missing-label checks apply to display and fenced equation blocks, not
inline math spans.
Inline math spans cover the trimmed source body, so symbol and parser diagnostics
point at the mathematical text rather than surrounding delimiter whitespace.
The legacy scanner and architecture frontend resolve Markdown regions in source
order: a code span, block/raw-text HTML region, or fence opened first owns later
dollar markers, while math opened first owns later backticks and fence-like text
until its first valid dollar close. Matching same-tag HTML blocks remain opaque
through nested blocks. Ordinary inline HTML tags protect only their tag lexemes,
so inline content remains live. Structural headings, anchors, fences, and syntax
diagnostics use the same opacity rules as math scanning. Their trimmed bodies and
spans therefore agree.
Markdown code spans use equal-length backtick delimiters and may contain shorter
backtick runs or line endings. Fenced-code closers require the matching marker,
at least the opener length, and no more than three leading spaces; a backtick
fence info string cannot contain a backtick.
TeX `\label{...}` inside Markdown math creates a label only when its backslash
begins an active control sequence.
MyST math labels are read only from the directive's leading option prefix.
An empty MyST role target is reported as malformed syntax.
Blank lines in that prefix are ignored; the prefix ends at the first nonblank
line that is not a directive option.
Only parsed Markdown links and MyST roles create reference facts; escaped role
markers, images, and link destinations or titles remain metadata rather than
references. The reference lexer supports inline links with balanced labels,
soft line breaks, bounded destinations, and nonblank multiline titles.
Parenthesized titles require literal parentheses to be backslash-escaped, and
valid named or numeric character references in destinations are decoded for
resolution. Reference-link definitions, autolinks, and the full CommonMark
inline-precedence graph remain outside this reference-fact profile and are left
as source text.
The destination/title separator permits spaces or tabs and at most one line ending;
quoted or parenthesized titles may span multiple nonblank lines. Unbracketed
destinations reject spaces and ASCII control characters; angle-bracket destinations
also reject unescaped angle brackets. Backslash escapes are decoded for reference
resolution while source offsets retain the original destination spelling. A local
fragment is recognized only when the decoded destination has a nonempty target after
`#`; empty fragments remain ordinary link metadata. Images remain metadata,
including nested images inside links; a link containing an image can still
contribute its outer target.
Role-like text inside inline code, inline or display math, HTML comments, and raw
HTML is opaque and does not create reference facts. Active MyST role bodies are
also opaque to Markdown-link tokenization, while ordinary inline HTML tag
lexemes do not hide their content.

## MyST structure linting

The architecture frontend lowers MyST headings, target anchors, fenced blocks,
directives, generic roles, equation roles, and code-cell facts. The structure
engine emits deterministic diagnostics for malformed ATX headings, unclosed
non-math fences, skipped heading levels, repeated top-level headings, generic
fences without an info string, malformed MyST directive openers,
malformed MyST directive options, malformed `{ref}`/`{eq}`/`{numref}` role
syntax, missing code-cell language arguments, and malformed code-cell tag lists.
Malformed ATX candidates are syntax issues only and do not enter heading, section,
slug, anchor, reference, or graph facts; a bare `#` and closing-hash-only forms
such as `# #` are valid empty headings.

This is a conservative lint subset, not a full MyST parser. Unknown custom
directive names remain allowed. Valid MyST target anchors such as `(label)=`
before headings are treated as anchors, not headings or malformed prose.
When the Markdown scanner is disabled, Markdown frontend and document-level
reference/structure analysis are skipped as well.

## Suppression comments

SciEqLint supports narrow source suppressions for Markdown and LaTeX:

```md
<!-- scieqlint-disable-next-line ALG001 -->
```

The Markdown next-line form applies only to math syntax on the immediately
following source line.

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

Path-based diagnostics, graph spans, and baseline identities retain the caller's
lexical input spelling. Relative inputs keep that spelling; absolute inputs are
rendered relative to the current working directory by default. For checks,
`--absolute-paths` retains an explicitly absolute input's lexical spelling.
Symlink targets are never resolved for presentation.
An absolute input on a different native root cannot be represented by the default
relative path model and is rejected without exposing that path. Checks can use
`--absolute-paths`; graph inputs must be expressed on the current native root.

## v0.1.3 LaTeX source subset

SciEqLint scans supported LaTeX display containers in `.tex` files:

- `\[ ... \]`
- `$$ ... $$`
- `equation` and `equation*`
- `align` and `align*`

For `align`, rows are split on unescaped `\\` and alignment markers are removed from
normalized equation text. Symbol diagnostics retain exact source positions across
removed comments, indentation, blank lines, and alignment markers; removed markers
remain lexical boundaries rather than joining adjacent symbol tokens. SciEqLint extracts
`\label{...}`, `\ref{...}`, and `\eqref{...}` for reference checks. LaTeX macro
expansion and full environment parsing are deferred.
Both `verbatim` and `verbatim*` environments are opaque. TeX controls are recognized
only when their backslash begins an active control sequence outside verbatim. Inside a
live verbatim range, every character is literal and the range ends at the first exact
matching `\end{verbatim}` or `\end{verbatim*}` sequence, regardless of line position,
percent signs, or preceding backslashes; mismatched starred forms remain literal
content. An unclosed range stays protected through end of file.

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
or `INP002` input diagnostics for malformed notebook inputs. JSON integers over
4096 decimal digits are rejected with `INP001`. Code-cell variable
analysis, notebook execution, and full Jupyter schema validation are deferred.
