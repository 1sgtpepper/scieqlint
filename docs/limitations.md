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

Path-based directory and glob discovery considers only these suffixes. An existing
explicit file with another suffix, or with no suffix, is rejected before scanning;
the path APIs raise `ValueError` and the CLI reports an operational error with exit
status 2. Already-loaded `SourceDocument` values with `DocumentKind.UNKNOWN` are
rejected by both document APIs. A missing explicit path keeps its `FileNotFoundError`
contract, and a nonexistent glob that matches no supported file remains empty.

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
core math facts. The generated-MyST profile additionally emits explicit GEN004
placeholder facts for standalone formula-not-decoded markers and complete empty
fenced, directive, and dollar-display containers, including accepted complete raw
LaTeX displays. Markers inside unsupported or incomplete raw environments remain
owned by their `UnknownMathFact` and do not become generated placeholders; unmatched
containers remain unclassified.

Raw LaTeX environments embedded in Markdown are scanned outside opaque code and
link regions. Complete `equation`, `align`, `flalign`, `gather`, and `multline`
forms, including their starred variants, are recognized as display math and may
produce `\label{...}`, `\ref{...}`, and `\eqref{...}` facts. Known non-math
containers such as `figure`/`figure*`, `table`/`table*`, `itemize`, and
`document` remain opaque.
Ownership is source ordered: a raw environment opened first makes later Markdown
links and MyST reference roles in its candidate opaque, while a Markdown link
opened first keeps ownership of its complete token.
Other raw environment candidates, including unsupported or incomplete forms, are
preserved as `UnknownMathFact` candidates. Complete unsupported environments
still preserve parseable equation label and reference facts; incomplete forms
do not. Explicit non-math and verbatim environments remain opaque and produce
neither math nor equation-reference facts. Markdown delimiters inside raw owners
cannot close or hide a math container or reference outside that source range.

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
before a valid ATX heading, including a bare or closing-only empty heading, are
treated as document-structure targets, so Markdown links such as `[](#label)` and
`[#label](#label)` do not emit equation-reference diagnostics when that target
exists. Missing-space forms such as `#Bad` are not headings, and orphaned
`(label)=` lines are not treated as valid targets. MyST `{ref}` roles to missing or
ambiguous generic targets use
generic-reference diagnostics instead of equation-reference diagnostics. This
also catches generated output that drops a heading anchor while preserving a
later `{ref}` to that anchor.

Strict missing-label checks apply to display and fenced equation blocks, not
inline math spans.
The opt-in `cross-format-references` profile reports `PORT001` when an equation
reference role is outside the conservative syntax baseline for the configured
`commonmark`, `myst`, `notebook`, or `typst` output profile. It materializes
reference facts from Markdown/MyST, LaTeX, and notebook source documents but does
not invoke an external renderer or guarantee output parity. Named profiles require
unique supplied document paths so fact and diagnostic identities remain stable.

Markdown/MyST displays recognize only complete, properly nested
`align`, `align*`, `aligned`, `alignedat`, and `split` environment pairs for
AMS classification. Incomplete fences and mismatched environment pairs retain
their enclosing display identity and do not create AMS semantic claims. A closed
dollar display is still a complete lexical container: even when its nested AMS
pair is incomplete or mismatched, its TeX label and reference tokens retain
lexical facts and source spans; an incomplete raw environment does not create
those facts. Rendered equation numbers and arbitrary TeX environment parsing
remain unsupported. Labels and references inside an aligned display retain the
enclosing display as their `source_block_id`; per-row identity and rendered
equation-number ownership are not modeled.
Inline math spans cover the trimmed source body, so symbol and parser diagnostics
point at the mathematical text rather than surrounding delimiter whitespace.
Non-empty `$...$`, `{math}` roles, and `\(...\)` spans become inline facts; the
fact also retains its surrounding source role (`heading`, `paragraph`,
`list-item`, or `blockquote`), including inherited list and blockquote continuation
ownership. A backslash-delimited span is active only when its backslash run is odd;
even runs are escaped according to the shared lexical scanner. An active nested
`\(` or `\)` inside a `\(...\)` candidate is retained as unsupported
`ambiguous_delimiter` math instead of being treated as a valid formula. LaTeX
parenthesis spans are confined to one normalized source line, and an active TeX
comment cannot supply their closing delimiter. Plain-text equation candidates scan
once around relation tokens and preserve integer and decimal operands with attached
unary signs. An unsupported attached group or malformed continuation rejects the
candidate instead of publishing a truncated prefix. Candidates remain unclassified until
`MathHost` classifies them symmetrically as `text-leak` or `not-math`; bare numeric
comparisons and signed prose remain excluded from math queries. Malformed or
unsupported inline math remains an `UnknownMath` fact rather than a guessed formula.
Unsupported TeX environment names,
including names with hyphens, digits, or underscores, are classified as unknown rather
than preserved. Only complete Markdown block items become generated equation-like
artifacts, so lazy container continuations remain non-artifacts. A candidate that overlaps code,
HTML, link metadata, or another MyST role is rejected without hiding a later disjoint
candidate, using the frontend's shared source-order ownership snapshot. Explicit math
inside Markdown link text remains visible for every supported delimiter, while link
destinations, titles, images, and inferred plain-text candidates in labels remain opaque.
Equation-like text detection is deliberately conservative and lexical rather than a
semantic parse. It only reports signals recognized by the current plain-text
classifier; non-ASCII or Greek identifiers, bare numeric comparisons, nested function
calls, trailing punctuation, and compact multi-word expressions without spaced
operators may remain ordinary text. Use a supported explicit math container when a
formula must be checked. `GEN005` is a suspicion about generated text, not a claim
that the text is a valid or mathematically correct equation, and SciEqLint does not
rewrite it.
The legacy scanner and architecture frontend resolve Markdown regions in source
order: a code span, block/raw-text HTML region, or fence opened first owns later
dollar markers, while math opened first owns later backticks and fence-like text
until its first valid dollar close. CommonMark HTML blocks use all seven standard
start and end conditions: type 1 (`pre`, `script`, `style`, and `textarea`) literal-
content blocks; type 2 comments; type 3 processing instructions; type 4 declarations;
type 5 CDATA; type 6 recognized block tags; and type 7 complete open or closing tags.
Types 1–5 include their terminating line and may retain blank lines, including
unindented blank list-item continuation lines; types 6–7 end before the next blank
line or at their container boundary. Type-7 complete tags do not interrupt paragraphs.
Ordinary inline HTML tags and comments protect only their own lexemes, so text between
tags remains live, while dedicated SciEqLint HTML comment directives remain active.
Structural headings, anchors, fences, and syntax diagnostics use the same opacity rules
as math scanning. Their trimmed bodies and spans therefore agree.
Markdown code spans use equal-length backtick delimiters and may contain shorter
backtick runs or line endings. Fenced math uses the CommonMark fence identity:
an opener has at least three matching backticks or tildes and at most three leading
spaces, and its info string is `math` or `{math}` after surrounding whitespace is
trimmed. A backtick opener's info string cannot contain a backtick. Fenced-code
closers require the matching marker, at least the opener length, and no more than
three leading spaces. A shorter, different-marker, or over-indented closer leaves
the math container unterminated and emits `SCAN001`; non-math fences remain opaque.
TeX `\label{...}` inside Markdown math creates a label only when its backslash
begins an active control sequence.
MyST math labels are read only from the directive's leading option prefix.
An empty MyST role target is reported as malformed syntax.
Blank lines in that prefix are ignored; the prefix ends at the first nonblank
line that is not a directive option.
Only parsed Markdown links and MyST roles create reference facts; escaped role
markers, images, and link destinations or titles remain metadata rather than
references, math, structure facts, or structure diagnostics. MyST roles do not
cross source-line boundaries. The reference lexer supports inline links with balanced
labels, soft line breaks within one inline container, destinations with up to 32 nested
parenthesis pairs, and nonblank multiline titles within one paragraph. Blank lines and
Markdown block starts end unmatched link labels and incomplete titles. Four-column or
tab-indented CommonMark code at a block boundary is opaque, including when nested in a
block quote or list; list indentation is measured from the item content column, while
indentation continuing an active paragraph remains prose. Fenced code and raw HTML use
the same container-relative line ownership, so quote and list prefixes do not expose
their literal contents as references. Setext underlines, thematic breaks, list markers,
and lazy nested-quote continuations follow their paragraph-interruption rules; in
particular, an ordered list interrupts a paragraph only when it starts at `1`, and an
empty list item does not interrupt it.
Parenthesized titles require literal parentheses to be backslash-escaped, and
valid named or numeric character references in destinations are decoded for
resolution. Reference-link definitions, autolinks, and the full CommonMark
inline-precedence graph remain outside this reference-fact profile and are left
as source text.
The destination/title separator permits spaces or tabs and at most one line ending;
quoted or parenthesized titles may span multiple nonblank lines in the same paragraph.
Unbracketed
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

## Generated-document formula checks

The `generated-myst` profile emits `GEN002` only for high-confidence artifacts
inside explicit inline or display math containers. It recognizes spaced TeX
commands such as `\A t t e n t { ... }` and spaced tokens that begin with an
uppercase letter and are followed by a parenthesized list of at least three
single-letter identifiers (for example,
`A t t e n t (Q, K, V)`) when the spaced token has at least four letters,
including at least two lowercase letters, plus the bounded garbled marker
`/C0 apod`. Valid spaced products, ordinary prose, code, escaped commands, TeX
comments, and other low-confidence text stay quiet; unsupported forms are not
guessed, and the default profile does not emit `GEN002`. The repeated-token scan is
bounded to 64 spaced segments; longer runs remain unsupported and quiet.

Formula placeholders such as `formula-not-decoded`, empty display math, and formula
image placeholders are reported separately by `GEN004` and remain outside `GEN002`.

### Bracketed LaTeX blocks

Under the `generated-myst` profile, `GEN003` flags a standalone `\[...\]` block
or a literal square-wrapper block (`[...]`) outside existing math, code, links,
HTML, and other opaque Markdown regions. Literal wrappers are reported only when
their body contains an unescaped TeX control word (for example, `\begin{array}`)
or a concise equation-like relation such as `x = y`, so ordinary bracketed prose
and Markdown links stay quiet. Literal wrappers use standalone opener and closer
lines. For the escaped form, a non-commented, unescaped `\]` may also close on the
opener line; either form may close with its unescaped closer
(`\]` or `]`) on its own later line in the same Markdown container. An opener that
reaches end of file or a Markdown ownership boundary first is incomplete. A
completed HTML/comment/fence/math block is also a boundary when the next line
starts directly without a blank line, while CommonMark HTML blocks that have not
terminated remain opaque. Source spans retain the exact source text, including
prefixes on list and blockquote continuation lines. Inline prose, escaped
openers, valid links, and bracketed text inside supported `$$` or MyST math stay
quiet; escaped closers do not complete a block. The diagnostic properties retain
the delimiter kind as `escaped` or `literal`. The default profile does not emit
`GEN003`.

`GEN004` flags explicit `formula-not-decoded` marker lines, complete empty dollar
displays, complete empty fenced or `{math}` directive containers, and standalone
formula image placeholders. Leading MyST option lines and TeX comment-only bodies
do not count as formula content in an otherwise empty `{math}` directive. The
standalone detector follows Markdown block ownership: Setext-heading text,
paragraph continuations, code, and opaque HTML content remain quiet, while an
owning HTML comment marker or a marker after a completed heading, fence, display,
or HTML block may start a new paragraph without a blank line. Unclosed empty
containers and unsupported image syntaxes remain unclassified; the detector does
not infer an intended formula.

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
not a unit database, and aliases must be listed explicitly. When dimension checking is
active, each numeric component in an input equation may contain at most 512 decimal
digits, and grouping may nest at most 64 parenthesis or brace groups. The digit limit
applies to numeric components, not digits inside identifiers or configured aliases. An
expression that exceeds either budget emits `DIM020` with a detail naming the limit;
checking continues for remaining expressions and documents.

## Symbols

Explicit Markdown and LaTeX `scieqlint-symbol` comments can define symbols for
the opt-in undefined-symbol check. SciEqLint does not infer symbols from prose.

## Notebooks

Notebooks are never executed. v0.1.4 scans Markdown cells, preserves notebook
cell metadata in diagnostics, ignores code cells, and emits deterministic `INP001`
or `INP002` input diagnostics for malformed notebook inputs. JSON integers over
4096 decimal digits are rejected with `INP001`. Code-cell variable
analysis, notebook execution, and full Jupyter schema validation are deferred.
