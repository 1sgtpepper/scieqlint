# Diagnostics

Diagnostic codes are user-facing API once introduced. The catalog may reserve
codes before every code is emitted by the current analyzer.

## Currently emitted

| Code | Default | Meaning |
|---|---|---|
| `ALG001` | error | Algebraic identity does not hold |
| `PARSE020` | info | Unsupported syntax; check skipped |
| `PARSE021` | info | Unsupported function; check skipped |
| `SCAN001` | warning | Unterminated math container |
| `INP001` | error | File could not be read or decoded |
| `INP002` | warning | Notebook schema issue; scanned best-effort |
| `SCAN010` | warning | Malformed explicit symbol directive |
| `STR001` | warning | ATX heading marker must be followed by a space |
| `STR002` | warning | Fenced block is missing its closing delimiter |
| `STR003` | info | Fenced code block has no language/info string |
| `STR004` | warning | Heading level skips an intermediate parent |
| `STR005` | warning | Document has more than one top-level heading |
| `DIR001` | warning | Malformed MyST directive fence |
| `DIR002` | warning | Malformed MyST directive option |
| `DIR010` | warning | Code-cell directive missing language |
| `DIR011` | warning | Malformed MyST role |
| `DIR012` | warning | Malformed code-cell tags |
| `REF001` | error | Duplicate equation label |
| `REF002` | warning | Equation reference target not found |
| `REF003` | info | Missing equation label in strict mode |
| `REF004` | warning | Missing generic reference target |
| `REF005` | warning | Ambiguous generic reference target |
| `REF006` | warning | Local reference path changes resolution after normalization |
| `REF007` | warning | Conflicting cross-reference metadata across output boundaries |
| `REF008` | warning | Equation reference matches a hidden or excluded target |
| `SUP001` | warning | Unknown suppression code |
| `DIM001` | error | Equation sides have different dimensions |
| `DIM002` | error | Addition or subtraction combines incompatible dimensions |
| `DIM010` | warning | Unknown variable dimension |
| `DIM020` | info | Dimension check skipped |
| `SYM001` | warning | Undefined symbol used before explicit definition |
| `PORT001` | warning | Equation reference syntax may not survive the configured output profile |
| `PORT002` | warning | Inline math lacks accessible text metadata |
| `PORT003` | warning | Equation syntax may not survive Typst export |
| `PORT004` | warning | Cell renderings conflict with cross-reference options |

`DIM020` also covers dimension expressions that exceed a parser resource budget. The
diagnostic detail identifies whether the expression exceeded the 512-decimal-digit
numeric-component limit or the 64-level group-nesting limit. Over-budget expressions
are skipped; analysis continues with later expressions and documents.


## Portability engine

`PORT001` is opt-in through the `cross-format-references` profile. It is
emitted from equation-reference and output-profile facts, not by reporters or
external renderer execution. JSON and SARIF results include `profile`,
`output_profile`, `ref_kind`, and `target` metadata.

`PORT002` is opt-in through `math-accessibility`. It reports explicit inline
math facts whose `alt` metadata is absent. Inferred equation-like prose is not
treated as an owned math span, and SciEqLint does not synthesize accessible
text. JSON and SARIF include the accessibility requirement, delimiter kind,
surrounding text role, and parse status recorded by the frontend.

`PORT003` is opt-in through `typst-portability`. It reports only the focused
display-math forms modeled by the frontend: `\dfrac`, `\argmin`, and
`aligned`, `array`, or `matrix` environments combined with `\left` or
`\right`. Diagnostics retain the exact source span and command or environment
metadata. The profile does not render Typst or claim complete translation
coverage.

`PORT004` is opt-in through `notebook-crossrefs`. It reports executable Markdown
or notebook code cells that combine `renderings` with a cross-reference label or
caption option. Notebook diagnostics retain logical cell locations, normalized
cell options, and the originating cell fact ID. SciEqLint does not execute or
re-render notebook outputs.

## REF008

`REF008` warns when an equation reference has a matching label fact from a hidden or
excluded source. Visible labels continue to define ordinary resolution; hidden and excluded
labels are retained as separate facts and do not create `REF001` duplicates by themselves.
The rule does not read ignored files or change project include/exclude behavior.

## Generated-output engine

`GEN001` and `GEN002` are emitted by the generated-output engine when callers
provide source-to-generated provenance facts. Source kind and conversion stage
are retained per generated document when supplied on its `SourceOrigin`; an
explicit profile value is only a fallback for an origin field that the caller
left unspecified. Missing origin metadata is never inferred. If a diagnostic
has more than one provenance fact, `provenance_ids` retains every fact ID and
the serialized metadata uses deterministic `provenance_1_*`,
`provenance_2_*`, and later keys instead of discarding all but the first fact.

| Code | Default | Meaning |
|---|---|---|
| `GEN001` | warning | Generated output is missing a preserved source anchor |
| `GEN002` | warning | Generated math contains suspicious formula text |
| `GEN003` | warning | Nonstandard bracketed LaTeX display block |
| `GEN004` | warning | Generated output contains a formula placeholder |
| `GEN005` | warning | Standalone text block looks like an equation |

## Reserved in catalog

These codes are present in `src/scieqlint/diag/catalog.py` for stable
documentation and reporter metadata, but the current analyzer does not currently
emit them from normal checks:

| Code | Default | Meaning |
|---|---|---|
| `ALG010` | warning | Identity assumes nonzero denominator |
| `ALG020` | info | Algebra check skipped |
| `ALG030` | warning | Algebra check exceeded configured limit |
| `PARSE001` | warning | Could not parse supported-looking math |
| `PARSE022` | info | Unsupported operator; check skipped |
| `SCAN002` | info | Inline math skipped by config |
| `INP003` | warning | File exceeded configured limit |
| `CFG001` | error | Invalid config file |
| `CFG010` | error | Invalid dimension expression |

## Example: ALG001

Input:

```tex
(a+b)^2 = a^2 + b^2
```

Output:

```text
ALG001 algebraic identity does not hold
  equation: (a+b)^2 = a^2 + b^2
  detail: left - right = 2*a*b
```

## Example: REF002

Input:

```md
See {eq}`missing`.
```

Output:

```text
REF002 equation reference target not found: missing
```

## Example: REF004

Input:

```md
See {ref}`missing`.
```

Output:

```text
REF004 missing generic reference target: missing
```

## Severity controls

The current loader does not implement `[severity]` overrides. Current
severity-affecting controls are exposed through documented CLI/config switches:
`--strict-unknowns` escalates parse-unknown diagnostics, strict missing-label
mode emits `REF003`, and `unknown_variables = "ignore"` suppresses `DIM010` when
dimension checks are active.

## REF006

`REF006` warns when a local cross-document reference resolves only after lexical
project-path normalization, for example when `./chapter.md` must be normalized to
`chapter.md`. External URLs and fragment-only references are not project paths.

## REF007

`REF007` warns when separate source or engine-output boundaries describe the same
logical cross-reference target with conflicting kind or display metadata. Source
format is retained as provenance and does not conflict by itself. The diagnostic
properties preserve both boundary identities; reporters do not inspect source
documents to reconstruct them.
