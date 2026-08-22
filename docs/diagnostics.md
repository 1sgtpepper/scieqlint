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
| `INP003` | warning | Input exceeded fixed safety limit |
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
| `REF011` | warning | Ambiguous equation reference |
| `REF006` | warning | Local reference path changes resolution after normalization |
| `REF007` | warning | Conflicting cross-reference metadata across output boundaries |
| `REF008` | warning | Equation reference matches a hidden or excluded target |
| `REF009` | warning | Non-heading reference has missing or generic display text |
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
math facts whose `alt` metadata is absent, including explicit math in notebook
Markdown cells. Inferred equation-like prose is not treated as an owned math span,
and SciEqLint does not synthesize accessible text. JSON and SARIF include the
accessibility requirement, delimiter kind, surrounding text role, parse status
recorded by `MathHost`, and the stable `accessibility_id` used as the
`check_documents()` metadata key. The diagnostic also retains `subject_fact_id`
for fact provenance; that ID is not a metadata lookup key. Callers provide
source-owned accessibility-ID-keyed metadata through `check_documents()`;
malformed, unknown, or ambiguous IDs are rejected even when no selected document
produces an accessibility snapshot. Notebook code and recorded outputs are facts
only; this profile never executes code or renders an output. LaTeX documents remain
outside the accessibility profile.

`PORT003` is opt-in through `typst-portability`. It reports only the focused
display-math forms modeled by `MathHost`: `\dfrac`, `\argmin`, and
`aligned`, `array`, or `matrix` environments combined with `\left` or
`\right` in Markdown and LaTeX documents. Notebook Markdown cells have exact
frontend source mapping but are not admitted by this portability profile.
Diagnostics retain the exact source span and command or environment metadata.
The profile does not render Typst or claim complete translation coverage.

`PORT004` is opt-in through `notebook-crossrefs`. It reports executable Markdown
or notebook code cells that combine `renderings` with a cross-reference label or
caption option, including Quarto's `lst-label`, `fig-subcap`, and `tbl-subcap`
aliases and options recorded on a notebook output. A conflict confined to cell
metadata produces one cell diagnostic; output-level metadata produces one diagnostic
for each affected recorded output and includes the relevant cell options. Notebook
diagnostics retain logical cell locations, exact JSON
output locations when an output supplies the cross-reference metadata, normalized
cell options, and the originating fact IDs. SciEqLint does not execute or re-render
notebook outputs.

## REF008

`REF008` warns when an equation reference has a matching label fact from a hidden or
excluded source. Visible labels continue to define ordinary resolution; hidden and excluded
labels are retained as separate facts and do not create `REF001` duplicates by themselves.
When only non-visible matches exist, `ReferenceEngine` reports `REF008` instead of also
reporting generic `REF002`; a target with no matching label still reports `REF002`.
The diagnostic reports exact visible, hidden, and excluded target counts. To keep output
bounded when many sources define the same label, it includes at most one deterministic
example document and provenance fact from each non-visible category.
The rule does not read ignored files or change project include/exclude behavior.

## REF009

`REF009` is opt-in through `reference-display`. It reports resolved non-heading targets
whose display text is absent or only repeats the target/type, including visible notebook
code-cell and recorded-output targets. Heading targets and untitled/default-display
typed `{eq}`/`{numref}` or TeX `\ref`/`\eqref` forms remain quiet; explicitly titled
typed roles are checked like other explicit display text. Diagnostics retain the explicit display span when one exists, target type,
reference kind, display intent, the selected canonical target identity, and originating fact
IDs. The canonical identity is the normalized member path plus fragment; the requested
display label remains a separate value. The rule does not render final prose or enforce a
universal writing style. For explicit Markdown/MyST labels, the `display_text` property is the
source label after surrounding whitespace is trimmed; inline markup, HTML entities, and
backslash escapes remain unchanged. Its diagnostic span points to that source text rather than
to rendered output.

## Generated-output engine

`GEN001` is emitted when callers provide source-to-generated provenance facts
and a preserved source anchor is missing from the generated document. `GEN002`
is emitted for suspicious generated math and does not require provenance;
caller-supplied provenance enriches it when available. Source kind and
conversion stage are retained per generated document when supplied on its
`SourceOrigin`; an explicit profile value is only a fallback for an origin
field that the caller left unspecified. Missing origin metadata is never
inferred. `GEN004` covers explicit `formula-not-decoded` markers, empty dollar,
fenced, or recognized raw display-math containers, and standalone formula image
placeholders. An ordinary rendered equation image without placeholder evidence
is not a placeholder.
If a diagnostic has more than one provenance fact, `provenance_ids`
retains every fact ID and the serialized metadata uses deterministic
`provenance_1_*`, `provenance_2_*`, and later keys instead of discarding all but
the first fact.

| Code | Default | Meaning |
|---|---|---|
| `GEN001` | warning | Generated output is missing a preserved source anchor |
| `GEN002` | warning | Generated math contains suspicious formula text |
| `GEN003` | warning | Nonstandard bracketed LaTeX display block (`\[...\]` or `[...]`) |
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

## Example: REF011

Input:

```md
$$x = 1$$ {#shared}
$$y = 2$$ {#shared}

See {eq}`shared`.
```

Output:

```text
REF001 duplicate equation label: shared
REF011 ambiguous equation reference: shared
```

## Severity controls

The current loader does not implement `[severity]` or profile-local severity
overrides. Portability diagnostics are warning-level and disabled unless their
validation profile is selected. Other severity-affecting controls are exposed
through documented CLI/config switches:
`--strict-unknowns` escalates parse-unknown diagnostics, strict missing-label
mode emits `REF003`, and `unknown_variables = "ignore"` suppresses `DIM010` when
dimension checks are active.

## REF005

`REF005` reports every supported generic reference whose selected member contains
more than one matching target, including MyST `{ref}` roles and local Markdown links.
Path-bearing and fragment-only links use the normalized member path plus fragment, so
equal labels in different members do not create ambiguity by themselves.

## REF006

`REF006` warns when a local cross-document reference resolves only after lexical
project-path normalization, for example when `./chapter.md` must be normalized to
`chapter.md`. Path-bearing links resolve by the pair `(normalized project path,
fragment)`; a matching fragment in another document does not satisfy the link.
Destination path and fragment components use valid UTF-8 percent-decoding and
native Windows separators before normalization. Destinations that are malformed,
external, have an empty decoded fragment, or escape the configured project root are
ignored as unsupported links; fragment-only references remain in the source member
and are not project paths.
Diagnostic properties include the selected normalized path-and-fragment identity
when a target is selected.

## REF007

`REF007` is the fact-backed diagnostic for separate source or engine-output boundaries
that describe the same complete normalized path-and-fragment identity with conflicting
kind or target metadata. Built-in notebook code/output metadata supplies distinct
recorded-output boundaries, so ordinary `check_paths()` and `check_documents()` calls
can report this conflict without executing a notebook. Arbitrary external or engine
producer facts are not a public input surface. When the source format has no path
identity, the normalized label remains the target key for a reference use.
Target-definition metadata must carry a member path; incomplete definitions are not
grouped by label. Source format is retained as provenance and does not conflict by
itself. A reference role or local display title belongs to the reference use and does
not participate in this comparison. The diagnostic properties preserve both boundary
identities; reporters do not inspect source documents to reconstruct them. Small
metadata dictionaries remain exact in the diagnostic detail. Oversized metadata uses
a deterministic key-and-value-length preview capped at 256 characters per boundary;
the complete metadata facts still determine whether a conflict exists.
