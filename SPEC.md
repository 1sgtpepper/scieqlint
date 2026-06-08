# SciEqLint Engineering Spec v11.1 — Complete OSS Implementation Input

Repository: `scieqlint`  
Package: `scieqlint`  
CLI: `scieqlint`  
Python: 3.11+  
Default license: MIT  
Spec status: polished implementation input with OSS contributor pass  
Supersedes: v10 and v11 draft  
Primary change: v0.1 is narrowed to the smallest credible public wedge; later capabilities are split into short, time-boxed releases with explicit cut rules.
Contributor pass: adds a first-class onboarding path, issue taxonomy, PR flow, maintainer review expectations, and starter issue map.

SciEqLint is a deterministic quality linter for scientific documents. It scans supported writing formats, extracts supported equation markup, checks exact scalar algebra where possible, validates equation labels and references, and reports stable diagnostics for local use, CI, JSON API consumers, and later editor integrations.

The product wedge is deliberately small:

> First win: catch obviously false scalar equations and broken equation references in Markdown/MyST scientific docs before review.

Everything else is sequenced after that first win. This document is intentionally strict about release boundaries: the project earns trust by shipping narrow, exact capabilities, not by claiming broad mathematical coverage early.

Recommended reading order for implementers: product contract, time-boxed release ladder, v0.1.0 scope, data contracts, parser/algebra boundaries, reporters, testing, and release checklist.

Recommended reading order for new contributors: README first screen, contributor quickstart, issue labels, first ten issues, narrow PR rules, tests/golden outputs, and limitations page.

Complete pack note: this repository tracks the full release ladder through v1.0.0. The current implementation covers the v0.1.5 analyzer slice behind fixtures, docs, CI, and acceptance gates; later roadmap items remain explicitly scoped below.

---

## 0. Decision record

v10 was strong but overstuffed for a first release. v11.1 keeps the core architecture and trust model, but changes release execution.

### Major scope changes from v10

| Area | v10 placement | v11.1 placement | Reason |
|---|---:|---:|---|
| Markdown/MyST display math | v0.1 | v0.1 | Core wedge; keep. |
| Equation labels/references | v0.1 | v0.1 | Strong zero-config value; keep. |
| Minimal parser + algebra | v0.1 | v0.1 | Demo-defining value; keep. |
| Text + JSON reporters | v0.1 | v0.1 | Local + automation foundation; keep. |
| JSON Schema | v0.1 | v0.1 | Cheap enough; keeps integrations honest. |
| GitHub annotations | v0.1 | v0.1.1 | Useful, but not required for first correctness loop. |
| pre-commit metadata | v0.1 | v0.1.1 | Adoption polish after core proof. |
| Dimensions | v0.1 | v0.1.2 | Valuable but config-heavy; should not distract from zero-config wedge. |
| LaTeX scanner | v0.1 | v0.1.3 | Important, but a separate source-location problem. |
| Notebook scanner | v0.1 | v0.1.4 | Important, but notebook cell spans deserve their own release. |
| SARIF + Action | v0.1.1 | v0.1.5 | Keep, but after GitHub annotations, dimensions, LaTeX, notebook MVP. |
| Suppressions + presets | v0.2 | v0.2 | Keep. |
| Graph export | v0.3 | v0.3 | Keep. |
| Symbols | v0.4 | v0.4 | Keep. |

### Operating principle

A release date does not move because a nice-to-have is unfinished. Scope is cut before the date moves. Dates move only for correctness, security, or packaging defects that would damage trust.

---

## 1. Normative language

`MUST`, `MUST NOT`, `SHOULD`, and `MAY` are used as release requirements.

- `MUST`: required for the named release.
- `MUST NOT`: forbidden unless this spec changes first.
- `SHOULD`: required unless a PR documents a reason not to.
- `MAY`: optional.

A requirement belongs to the earliest release named beside it. Later releases inherit previous requirements unless explicitly changed.

---

## 2. Product contract

SciEqLint is a deterministic CI linter for equations and equation-adjacent structure in scientific documents.

Given the same files, config, and SciEqLint version, the tool MUST emit the same diagnostics in the same order. Supported math is checked exactly. Supported labels and references are checked deterministically. Unsupported math is reported as unknown or skipped. The checker MUST NOT guess.

### Product promise

SciEqLint does three things well, in this order:

1. Catch equation reference mistakes that deterministic scanners can see.
2. Catch exact scalar algebra mistakes in a deliberately small grammar.
3. Catch configured physical-dimension mistakes once users opt into dimension metadata.

### Non-negotiable trust rules

The checker runtime MUST NOT:

- make network calls,
- execute notebooks,
- import user project modules,
- evaluate Python code from documents,
- run shell commands from analysis core,
- parse user-controlled math text through SymPy text parsers,
- silently infer unsupported math,
- emit timestamps or machine-specific paths in JSON by default.

### Anti-overclaiming rule

The README, docs, diagnostics, and release notes MUST say “supported subset” instead of implying broad mathematical understanding.

Bad positioning:

> SciEqLint verifies scientific equations.

Good positioning:

> SciEqLint catches exact scalar algebra mistakes and broken equation references in a documented subset of scientific documents.

---

## 3. Target users

Primary early users:

- Scientific Python maintainers with Markdown docs.
- Jupyter Book and MyST authors.
- Open textbook authors.
- Research software engineers maintaining docs and examples.
- Students writing Markdown reports.
- Paper and documentation authors who want broken equation references caught before review.

Secondary users after v0.1.3+:

- LaTeX paper authors.
- Lab documentation maintainers.
- Sphinx/Jupyter Book projects with mixed Markdown, notebooks, and LaTeX.
- CI maintainers for scientific projects.
- Editor-extension authors consuming JSON.

Not v0.x users:

- Full theorem-proving projects.
- General CAS users.
- Tensor calculus systems.
- PDE symbolic manipulation users.
- Notebook execution workflows.
- Runtime unit-checking libraries.

---

## 4. Time-boxed release ladder

Dates below assume implementation starts Monday, 2026-06-08. If implementation starts later, shift every date by the same number of days. Durations are normative. Calendar dates are planning anchors.

| Release | Time box | Planning window | User-facing reason | Ships | Explicitly does not ship |
|---|---:|---|---|---|---|
| v0.0.1 | 1 week | 2026-06-08 to 2026-06-14 | installable skeleton | package, CLI shell, config defaults, CI skeleton | real checks |
| v0.1.0 | 4 weeks | 2026-06-15 to 2026-07-12 | catch bad equations and broken refs in Markdown/MyST | Markdown/MyST scanner subset, labels/references, parser, algebra, text, JSON, JSON Schema, demo | dimensions, LaTeX files, notebooks, GitHub annotations, SARIF |
| v0.1.1 | 1 week | 2026-07-13 to 2026-07-19 | make PR annotations easy | GitHub reporter, pre-commit metadata, CI docs | new math behavior |
| v0.1.2 | 2 weeks | 2026-07-20 to 2026-08-02 | catch configured dimension mistakes | dimension engine, `[vars]`, dimension diagnostics | presets, aliases, unit database |
| v0.1.3 | 2 weeks | 2026-08-03 to 2026-08-16 | support LaTeX source files | LaTeX container scanner, LaTeX labels/references | full LaTeX parser, macro expansion |
| v0.1.4 | 1 week | 2026-08-17 to 2026-08-23 | support notebook Markdown cells | `.ipynb` markdown-cell scanner, cell spans | notebook execution, code-cell variable analysis |
| v0.1.5 | 1 week | 2026-08-24 to 2026-08-30 | support code scanning | SARIF reporter, thin GitHub Action wrapper | new scanner/math behavior |
| v0.2.0 | 3 weeks | 2026-08-31 to 2026-09-20 | fit serious docs workflows | suppressions, presets, aliases, optional scalar functions if time remains | graph, symbol inference |
| v0.3.0 | 2 weeks | 2026-09-21 to 2026-10-04 | make equations navigable | graph JSON export | natural-language symbol parsing |
| v0.4.0 | 3 weeks | 2026-10-05 to 2026-10-25 | catch undefined symbols and notation drift | symbol table, explicit directives, symbol diagnostics | prose inference |
| v0.5.0 | 4 weeks | 2026-10-26 to 2026-11-22 | run well on books/sites | project mode, baselines, file order | plugin API |
| v0.9.0 | 4 weeks | 2026-11-23 to 2026-12-20 | stabilize contracts | performance pass, compatibility pass, contract candidates | large new features |
| v1.0.0 | acceptance-gated | no earlier than 2027-Q1 | stable scientific CI core | frozen CLI/JSON/SARIF/config/API | experimental defaults |

### Time-box enforcement

Each release has three possible outcomes at the deadline:

1. Ship if release checks pass.
2. Cut unfinished optional scope and ship.
3. Do not ship if correctness/security/package trust is broken.

A release MUST NOT absorb the next release’s features to “make the release feel bigger.”

### Release definition of done

A release is done only when all of the following are true:

- the release checklist for that release passes,
- user-facing docs show the shipped behavior and its limits,
- contributor-facing docs show how to run, test, and safely change the shipped behavior,
- golden fixtures lock expected output,
- the diagnostic catalog and schemas are updated when applicable,
- issue labels and starter issues reflect the current release scope,
- a clean wheel install smoke test passes,
- release notes explicitly list deferred scope.

A feature without docs and fixtures is not shipped.

### Maximum work in progress

At any time, only one of these layers may be actively changing in a PR unless the change is mechanical and tests prove the coupling:

- scanner,
- parser,
- checker,
- reporter/schema,
- config,
- docs/governance,
- packaging/CI.

### Scope-lock rule

At the start of each release, maintainers must mark every planned item as one of:

- **required**: must ship for the release to be meaningful,
- **cuttable**: may be deferred without breaking the release promise,
- **forbidden**: belongs to a later release and must not enter the current branch.

The hard cut lists in this spec are the default source of truth.

---

## 5. Release scope details

### 5.1 v0.0.1 — installable skeleton

Goal: prove the package can install, run, and pass the basic quality loop.

Time box: 1 week.

Ships:

- `src/scieqlint` package.
- `scieqlint` console script.
- `python -m scieqlint` entry point.
- CLI commands exist: `check`, `init`, `demo`, `explain`.
- `check` can discover files and return “no checks implemented” without crashing.
- Config defaults load.
- Ruff, Pyright, pytest, wheel build, wheel install smoke.
- `py.typed` included.
- `CONTRIBUTING.md`, `ROADMAP.md`, `SECURITY.md`, `SUPPORT.md`, `CODE_OF_CONDUCT.md`, and `MAINTAINERS.md` exist.
- GitHub issue templates and PR template exist.
- `GOOD_FIRST_ISSUES.md` lists at least ten starter issues.

Acceptance:

```bash
scieqlint --help
scieqlint check README.md
scieqlint demo
python -m scieqlint --help
```

Deferred:

- scanners,
- parser,
- real diagnostics,
- docs site.

### 5.2 v0.1.0 — Markdown/MyST zero-config MVP

Goal: useful on a real Markdown/MyST scientific repo before config exists.

Time box: 4 weeks.

v0.1.0 intentionally ships only these source formats:

- `.md`
- `.markdown`

v0.1.0 does not scan `.tex` or `.ipynb`. Discovered `.tex` and `.ipynb` files MAY be ignored quietly. Explicitly passed unsupported files SHOULD produce a clear unsupported-kind diagnostic or CLI message.

#### v0.1.0 CLI

Required commands:

```bash
scieqlint check [PATH_OR_GLOB...]
scieqlint init
scieqlint demo
scieqlint explain CODE
```

Required check options:

```bash
--config PATH
--format text|json
--output PATH
--no-algebra
--inline-math
--quiet
--strict-unknowns
--absolute-paths
```

Not v0.1.0:

```bash
--format github      # v0.1.1
--format sarif       # v0.1.5
--dimension          # v0.1.2
--no-dimension       # v0.1.2
--show-suppressed    # v0.2.0
```

#### v0.1.0 supported Markdown/MyST math forms

Supported display math:

```md
$$
(a+b)^2 = a^2 + b^2
$$
```

Supported fenced math:

````md
```math
E = mc^2
```
````

Supported MyST math directive:

````md
```{math}
:label: energy
E = mc^2
```
````

Supported labels:

```md
$$
E = mc^2
$$ {#eq-energy}
```

```md
$$
E = mc^2
$$ (energy)
```

```md
$$ \label{eq:energy} E = mc^2 $$
```

````md
```{math}
:label: energy
E = mc^2
```
````

Supported references:

```md
See [Eq.](#eq-energy).
See [](#eq-energy).
See {eq}`energy`.
See {numref}`energy`.
See {numref}`Eq. %s <energy>`.
```

Inline math is opt-in and parse failures from inline math MUST be low severity by default.

#### v0.1.0 parser scope

Supported grammar:

```text
equation_group : equation (line_sep equation)*
equation       : expr "=" expr ("=" expr)*
expr           : sum
sum            : product (("+" | "-") product)*
product        : power (("*" | "/" | implicit_mul) power)*
power          : unary ("^" signed_integer)?
unary          : ("+" | "-") unary | atom
atom           : NUMBER | SYMBOL | group | frac | sqrt
group          : "(" expr ")" | "{" expr "}"
frac           : "\\frac" group group
sqrt           : "\\sqrt" group | "\\sqrt" "(" expr ")"
```

Supported aliases:

- `\cdot` -> `*`
- `\times` -> `*`
- `{...}` as grouping
- `^2`, `^{-1}`, `^-1`

Unsupported in v0.1.0:

- trigonometric functions,
- logarithmic and exponential functions,
- integrals,
- derivatives,
- limits,
- sums/products,
- matrices,
- vectors/tensors,
- inequalities,
- approximate equality,
- non-integer powers except `sqrt`,
- user-defined TeX macros,
- Greek alias normalization.

Unsupported syntax MUST emit an unknown/skipped diagnostic, not an exception.

#### v0.1.0 algebra scope

Algebra check supports:

- rational numbers,
- symbols,
- addition,
- subtraction,
- multiplication,
- division,
- unary signs,
- integer powers,
- `sqrt` only when exact handling is possible.

Algorithm:

1. Convert SciEqLint AST to SymPy objects.
2. Never pass document text to SymPy parsers.
3. Compute `left - right` for adjacent equality sides.
4. Apply constrained rational/polynomial simplification using `together` and `cancel`.
5. Emit `ALG001` only when nonzero residual is proven.
6. Emit unknown/skipped diagnostics for everything else.

Avoid `sympy.simplify` in v0.1.0.

#### v0.1.0 references scope

Checks:

- duplicate labels -> `REF001` error,
- missing supported reference targets -> `REF002` warning by default,
- unlabeled equation blocks -> `REF003` only in strict mode.

Reference checking MUST work with no config file.

#### v0.1.0 reporters

Ships:

- text reporter,
- JSON reporter,
- JSON Schema artifacts.

Text output example:

```text
examples/bad/famous_bad.md:5:1: error ALG001 algebraic identity does not hold
  equation: (a+b)^2 = a^2 + b^2
  detail: left - right = 2*a*b
```

JSON output MUST be deterministic, timestamp-free, and suitable as the first automation contract.

#### v0.1.0 acceptance

Required demo:

```tex
(a+b)^2 = a^2 + b^2
```

Expected diagnostic:

```text
ALG001: algebraic identity does not hold; left - right = 2*a*b
```

Required reference demo:

```md
See {eq}`missing`.
```

Expected diagnostic:

```text
REF002: equation reference target not found: missing
```

Required commands:

```bash
scieqlint demo
scieqlint check examples/bad/famous_bad.md
scieqlint check examples/bad/famous_bad.md --format json
scieqlint check examples/bad/references_bad.md
scieqlint init
scieqlint explain ALG001
scieqlint explain REF002
python -m scieqlint check examples/bad/famous_bad.md
```

Required fixtures:

```text
tests/fixtures/good/algebra_good.md
tests/fixtures/bad/famous_bad.md
tests/fixtures/good/references_good.md
tests/fixtures/bad/references_bad.md
tests/fixtures/good/myst_good.md
tests/fixtures/bad/myst_bad.md
```

Required golden outputs:

```text
tests/golden/text/*.txt
tests/golden/json/*.json
```

Required CI gates:

- Ruff format check.
- Ruff lint.
- Pyright.
- import-linter.
- pytest with coverage.
- JSON schema validation for golden JSON.
- wheel build and clean venv smoke.
- docs smoke until the docs site exists; MkDocs strict build once the docs site exists.

Hard cut list if late:

1. Cut denominator warnings.
2. Cut fancy `{numref}` title parsing while keeping simple `{numref}`.
3. Cut `init` polish, but not the command.
4. Cut inline math support entirely.

Do not cut:

- algebra demo,
- reference demo,
- deterministic JSON,
- unsupported-math safety behavior,
- limitations docs.

### 5.3 v0.1.1 — GitHub annotations and pre-commit

Goal: make the MVP useful in pull requests without changing analysis behavior.

Time box: 1 week.

Ships:

- `--format github`.
- GitHub workflow command reporter.
- workflow command escaping tests.
- `.pre-commit-hooks.yaml`.
- README PR annotation snippet.
- pre-commit setup docs.

GitHub reporter maps severities:

| SciEqLint | GitHub command |
|---|---|
| error | `error` |
| warning | `warning` |
| info | `notice` |

Reporter MUST escape:

- `%` as `%25`,
- `\r` as `%0D`,
- `\n` as `%0A`,
- `,` and `:` in properties where required by GitHub workflow command syntax.

Acceptance:

```bash
scieqlint check examples/bad/famous_bad.md --format github
```

Must emit a valid annotation with file, line, column, and diagnostic title.

Hard rule: v0.1.1 MUST NOT add parser, scanner, dimension, or algebra features.

### 5.4 v0.1.2 — dimension MVP

Goal: catch dimension mistakes once users provide small config.

Time box: 2 weeks.

Ships:

- dimension vector engine,
- `[vars]` config,
- `[checks.dimension]` config,
- `--dimension`,
- `--no-dimension`,
- dimension diagnostics,
- dimension docs and demo.

Dimension model:

```text
(M, L, T, I, Theta, N, J)
```

Dimension config example:

```toml
[vars]
m = "M"
c = "L T^-1"
E = "M L^2 T^-2"
```

Activation:

```toml
[checks.dimension]
mode = "auto" # "auto" | "on" | "off"
unknown_variables = "warn"
```

Rules:

- `auto` runs only when `[vars]` is non-empty.
- Zero-config mode MUST NOT emit unknown-variable dimension noise.
- `on` runs and applies unknown-variable policy.
- `off` disables dimension checks.

Inference rules:

| Expression | Rule |
|---|---|
| number | dimensionless |
| symbol | config lookup or unknown |
| `a + b` | dimensions must match |
| `a - b` | dimensions must match |
| `a * b` | add vectors |
| `a / b` | subtract vectors |
| `a^n` | multiply vector by integer `n` |
| `sqrt(a)` | divide vector by 2 if all exponents even; else unknown |

Diagnostics introduced:

| Code | Default | Meaning |
|---|---:|---|
| `DIM001` | error | Equation sides have different dimensions |
| `DIM002` | error | Addition/subtraction combines incompatible dimensions |
| `DIM010` | warning | Unknown variable dimension |
| `DIM020` | info | Dimension check skipped |
| `CFG010` | error | Invalid dimension expression |

Acceptance:

- Zero-config mode emits no `DIM010` diagnostics.
- `F = m*a` passes with configured mechanics dimensions.
- `E = m*c` emits `DIM001` with configured dimensions.
- `E = m*c^2` passes.
- `x + t` emits `DIM002` when dimensions are configured.
- Unknown symbol emits `DIM010` only when dimension checking is active.

Hard cut list if late:

1. Cut `sqrt` dimension inference.
2. Cut `--dimension` and `--no-dimension` CLI flags, but keep config mode.
3. Cut detailed expression names from dimension detail output.

Do not cut:

- zero-config quiet behavior,
- `DIM001`,
- invalid dimension config errors.

### 5.5 v0.1.3 — LaTeX source MVP

Goal: support `.tex` files through a container scanner, not a full LaTeX parser.

Time box: 2 weeks.

Ships:

- `.tex` discovery,
- LaTeX display/container scanner,
- LaTeX label/reference extraction,
- source spans,
- tests and docs.

Supported containers:

```tex
\[ ... \]
$$ ... $$
\begin{equation} ... \end{equation}
\begin{equation*} ... \end{equation*}
\begin{align} ... \end{align}
\begin{align*} ... \end{align*}
```

For `align`, scanner MUST split rows on unescaped `\\` and remove `&` alignment markers before creating `MathBlock` objects.

LaTeX scanner MUST ignore:

- verbatim environments,
- comment-only math lines,
- math-like text in comments.

Supported labels/references:

```tex
\label{eq:energy}
\ref{eq:energy}
\eqref{eq:energy}
```

Diagnostics introduced or extended:

- `SCAN001`: unterminated math container.

Acceptance:

- LaTeX equation and align environments extracted.
- LaTeX labels extracted with stable spans.
- LaTeX refs and eqrefs extracted with stable spans.
- Duplicate labels and missing references work across Markdown and LaTeX together.
- Unterminated container warns, not crashes.

Hard cut list if late:

1. Cut `align` support.
2. Cut `$$ ... $$` in LaTeX files if ambiguity is high.
3. Cut source-span end columns, but keep start line/column.

Do not cut:

- `equation` environment,
- `\[ ... \]`,
- `\label`, `\ref`, `\eqref`.

### 5.6 v0.1.4 — notebook Markdown-cell MVP

Goal: scan notebook Markdown cells without execution.

Time box: 1 week.

Ships:

- `.ipynb` discovery,
- `nbformat` loading,
- Markdown-cell scanning through existing Markdown scanner,
- notebook cell metadata in diagnostics,
- malformed notebook handling.

Notebook scanner MUST:

- scan only markdown cells,
- ignore code cells without diagnostics,
- never execute notebooks,
- preserve zero-based cell index,
- preserve one-based cell line where possible.

Diagnostics introduced:

| Code | Default | Meaning |
|---|---:|---|
| `INP002` | warning | Notebook schema issue; scanned best-effort |

Acceptance:

- Notebook markdown cells scanned.
- Code cells ignored.
- Notebook references preserve cell metadata.
- Malformed JSON emits `INP001` and does not stop other files.
- Schema issue emits `INP002` when cells remain readable.

Hard cut list if late:

1. Cut best-effort schema-warning path and only handle valid notebooks.
2. Cut file-level line mapping.

Do not cut:

- no execution,
- markdown-cell scanning,
- cell index in JSON.

### 5.7 v0.1.5 — SARIF and thin GitHub Action

Goal: support GitHub code scanning and copy-pasteable CI without changing analysis behavior.

Time box: 1 week.

Ships:

- `--format sarif`,
- deterministic SARIF 2.1.0 subset,
- partial fingerprints,
- SARIF result-size guard,
- GitHub SARIF upload docs,
- thin composite action wrapper.

SARIF MUST include:

- `$schema`,
- `version = "2.1.0"`,
- `runs`,
- tool driver name,
- semantic version,
- one rule per diagnostic code,
- result `ruleId`,
- result `level`,
- message text,
- repo-relative POSIX artifact URI,
- region when span exists,
- deterministic partial fingerprint.

Fingerprint input:

```text
code + "\0" + normalized path + "\0" + line/col span + "\0" + normalized equation-or-target
```

The GitHub Action wrapper MUST be thin:

- checkout is user responsibility,
- set up Python,
- install package,
- run CLI,
- optionally write job summary from normal CLI or JSON output,
- no separate analyzer.

Acceptance:

- SARIF golden tests pass.
- SARIF sample workflow validates structurally.
- Result-size guard is deterministic.
- Composite action remains a CLI wrapper.

Hard rule: v0.1.5 MUST NOT change scanner, parser, algebra, reference, or dimension semantics.

### 5.8 v0.2.0 — serious docs workflow layer

Goal: reduce adoption friction in real repositories after the core is trusted.

Time box: 3 weeks.

Ships, in priority order:

1. Suppression comments.
2. Preset package data.
3. Alias normalization.
4. Scalar functions, but only if the first three items are complete by the midpoint of week 3.

#### Suppressions

Supported forms:

```md
<!-- scieqlint-disable-next-line DIM001 -->
```

```tex
% scieqlint-disable-current-block ALG001
```

Rules:

- Suppression scope must be narrow.
- Unknown suppression code emits warning.
- Suppressed diagnostics do not affect exit code.
- Suppressed diagnostics appear in JSON when `show_suppressed = true`.

#### Presets

Commands:

```bash
scieqlint presets list
scieqlint presets show mechanics
scieqlint init --preset mechanics
```

Initial presets:

- `mechanics`,
- `waves`,
- `thermodynamics`,
- `electromagnetism-basic`.

Presets are TOML templates, not a unit database.

#### Aliases

Config:

```toml
[aliases]
rho = ["\\rho", "ρ"]
theta = ["\\theta", "θ"]
```

Alias conflicts are config errors.

#### Optional scalar functions

If included, parser MAY support:

- `\sin`,
- `\cos`,
- `\tan`,
- `\exp`,
- `\log`,
- `\ln`.

Dimension rules:

- argument must be dimensionless,
- result is dimensionless.

Algebra identities involving these functions remain unknown unless later opt-in mode supports them.

Acceptance:

- Suppression comments work in Markdown and LaTeX.
- Suppressed diagnostics do not fail CLI.
- Presets list/show/init works.
- User config overrides presets.
- Alias normalization works if aliases included.
- `sin(v)` emits `DIM003` when scalar functions are included and `v` has velocity dimension.

Hard cut list if late:

1. Cut scalar functions.
2. Cut aliases.
3. Cut all but `mechanics` preset.

Do not cut:

- suppressions,
- suppression visibility in JSON,
- preset resource loading through `importlib.resources`.

### 5.9 v0.3.0 — graph export

Goal: make equations and references navigable.

Time box: 2 weeks.

Ships:

- graph data model,
- graph JSON schema,
- `scieqlint graph`,
- equation nodes,
- document nodes if needed,
- reference edges,
- stable sorted graph output.

Command:

```bash
scieqlint graph "docs/**/*.md" --output scieqlint-graph.json
```

Graph command MUST reuse the same scanning/parsing/checking pipeline as `check`. It MUST NOT implement a parallel analyzer.

Acceptance:

- LaTeX labels appear as graph nodes.
- Markdown labels appear as graph nodes.
- MyST labels appear as graph nodes.
- Equation references appear as graph edges.
- Graph JSON validates against schema.
- Graph output is stable across operating systems.

### 5.10 v0.4.0 — symbols

Goal: catch undefined variables and notation drift without natural-language inference.

Time box: 3 weeks.

Ships:

- symbol directive scanner support,
- symbol table,
- undefined-symbol check,
- dimension conflict on redefinition,
- project order config,
- symbol graph nodes/edges.

Supported directive:

```md
<!-- scieqlint-symbol: E = energy, dim="M L^2 T^-2" -->
```

```tex
% scieqlint-symbol: E = energy, dim="M L^2 T^-2"
```

Rules:

- Do not parse natural-language definitions.
- Symbol feature is disabled by default unless explicitly enabled.
- A symbol on LHS may introduce a definition when configured.

Acceptance:

- Symbol directives parsed.
- Undefined symbol check works across ordered files.
- Redefinition dimension conflicts emit `SYM002`.
- Symbol feature can be disabled cleanly.
- No prose inference.

### 5.11 v0.5.0 — project mode

Goal: support larger docs/books without changing core semantics.

Time box: 4 weeks.

Ships:

- better project discovery,
- explicit file ordering,
- diagnostic baselines,
- large-fixture performance pass,
- docs for book-style repositories.

Does not ship:

- plugin API,
- natural-language symbol extraction,
- remote analysis,
- notebook execution.

### 5.12 v0.9.0 and v1.0.0

v0.9.0 is a stabilization release, not a feature release.

v0.9.0 ships:

- compatibility matrix pass,
- performance pass,
- deprecation policy,
- contract freeze candidates,
- public corpus plan,
- migration docs.

v1.0.0 ships only when:

- CLI is frozen,
- JSON schema is frozen,
- SARIF behavior is frozen,
- config schema is documented,
- public API is documented,
- compatibility matrix is green,
- accuracy benchmark summary is published,
- performance budgets are met,
- at least 100 documented equation fixtures exist.

v1.0.0 MUST NOT be date-shipped if these conditions are not met.

---

## 6. Architecture

Use a functional core with adapter shells.

```text
CLI / pre-commit / GitHub Action / editor
        |
        v
app service
        |
        v
file discovery -> source loading -> scanning -> parsing -> checks -> diagnostics -> reporting
```

The core owns data contracts, parser output, checks, diagnostics, config semantics, and report schemas. Adapters own I/O, command-line plumbing, and integration-specific formatting.

### Dependency policy

Use maintained dependencies for generic plumbing. Own equation semantics and source-location contracts.

| Concern | Use | Earliest release | Boundary |
|---|---|---:|---|
| CLI | `click` | v0.0.1 | command parsing only |
| Markdown/MyST tokens | `markdown-it-py`, `mdit-py-plugins` | v0.1.0 | tokenization and narrow math extraction |
| Notebook | `nbformat` | v0.1.4 | schema-aware `.ipynb` loading |
| Ignore matching | `pathspec` | v0.1.0 | gitignore-style matching |
| Math grammar | `lark` | v0.1.0 | grammar parsing and transformer entry point |
| Algebra | `sympy` | v0.1.0 | exact expression backend behind local adapter |
| JSON Schema validation | `jsonschema` dev dependency | v0.1.0 | golden-output/schema tests only |
| Package resources | `importlib.resources` | v0.0.1 | grammar, schemas, examples, presets |
| Type checking | `pyright` | v0.0.1 | CI gate |
| Format/lint | `ruff` | v0.0.1 | CI gate |
| Tests | `pytest`, `coverage`, `hypothesis` | v0.0.1+ | unit, golden, property tests |
| Import boundaries | `import-linter` | v0.1.0 | architecture enforcement |
| Docs | `mkdocs`, `mkdocs-material` | v0.1.0 | strict docs build when docs site exists |
| Build/tool env | `uv` | v0.0.1 | sync, run, build |

SciEqLint MUST NOT depend on Sphinx, Jupyter Book, Pandoc, LaTeXML, ChkTeX, latexindent, or TexLab in core analysis.

### Package layout by v0.1.0

```text
src/scieqlint/
  __init__.py
  __main__.py
  py.typed
  api.py
  app.py
  cli.py

  config/
    __init__.py
    model.py
    load.py
    validate.py

  io/
    __init__.py
    discover.py
    source.py
    limits.py
    resources.py

  scan/
    __init__.py
    base.py
    markdown.py

  parse/
    __init__.py
    ast.py
    grammar.lark
    parser.py
    transform.py
    normalize.py
    print.py

  check/
    __init__.py
    algebra.py
    references.py

  diag/
    __init__.py
    model.py
    catalog.py

  report/
    __init__.py
    base.py
    text.py
    json.py

  schemas/
    scieqlint-result-0.1.schema.json
    scieqlint-diagnostic-0.1.schema.json

  examples/
    good/
    bad/
```

Add these modules only when their releases start:

```text
scan/latex.py             # v0.1.3
scan/notebook.py          # v0.1.4
check/dimensions.py       # v0.1.2
check/suppressions.py     # v0.2.0
check/symbols.py          # v0.4.0
report/github.py          # v0.1.1
report/sarif.py           # v0.1.5
graph/model.py            # v0.3.0
graph/export.py           # v0.3.0
presets/*.toml            # v0.2.0
```

Do not create `utils.py`, `helpers.py`, `core.py`, or `engine.py`. Split by domain.

### Import rules

`cli` MAY import `api` and reporter selection code. It MUST NOT import scanners, parser modules, or check modules directly.

`api` MAY import `app`, `config`, `diag`, and public data models.

`app` MAY orchestrate `io`, `scan`, `parse`, `check`, `report`, `config`, and `diag`.

`scan` MAY import `io.source`, `diag.model`, and `scan.base`. It MUST NOT import `parse`, `check`, or `report`.

`parse` MAY import `parse.ast`, `diag.model`, and source-span types. It MUST NOT import scanners, checks, reporters, config loaders, or SymPy.

`check` MAY import `parse.ast`, `diag`, `config.model`, and `graph` when graph exists. It MUST NOT import `scan`, `io.discover`, `report`, or `cli`.

`report` MAY import `diag.model`, result models, and packaged schema metadata. It MUST NOT import `scan`, `parse`, or `check`.

`config` MUST NOT import `cli`, `scan`, `parse`, `check`, or `report`.

`io.resources` MAY use `importlib.resources` to load package data. It MUST NOT import `scan`, `parse`, `check`, `report`, or `cli`.

These rules MUST be enforced by import-linter no later than v0.1.0.

---

## 7. Public API

v0.1.0 public API:

```python
from pathlib import Path
from scieqlint.api import check_paths, check_documents, load_config

result = check_paths([Path("README.md")], config_path=Path("scieqlint.toml"))
print(result.exit_code)
```

Required signatures:

```python
def check_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
) -> CheckResult: ...

def check_documents(
    documents: Sequence[SourceDocument],
    *,
    config: Config,
) -> CheckResult: ...

def load_config(path: Path | str | None = None) -> Config: ...
```

Rules:

- API calls MUST NOT print to stdout/stderr.
- API calls MUST NOT call `sys.exit`.
- API results MUST be deterministic.
- v0.x MAY change undocumented internals.
- v1.0 MUST freeze documented API names, JSON schema, and diagnostic codes.

---

## 8. Data contracts

### 8.1 SourceDocument

```python
@dataclass(frozen=True, slots=True)
class SourceDocument:
    path: PurePosixPath
    text: str
    kind: DocumentKind
    line_index: LineIndex
    display_path: str
```

Rules:

- `text` MUST be decoded UTF-8 unless config explicitly allows replacement.
- Newlines MUST be normalized to `\n` before scanning.
- `path` MUST be normalized to repo-relative POSIX path where possible.
- `display_path` MUST be stable across operating systems.

`DocumentKind` values by release:

```python
class DocumentKind(Enum):
    MARKDOWN = "markdown"   # v0.1.0
    LATEX = "latex"         # v0.1.3
    NOTEBOOK = "notebook"   # v0.1.4
    UNKNOWN = "unknown"
```

### 8.2 LineIndex

`LineIndex` maps Python string character offsets to one-based line and column.

Requirements:

- Offsets are Python string character offsets, not UTF-8 byte offsets.
- Lines and columns in diagnostics are one-based.
- `LineIndex.position(offset)` MUST be O(log n) or better.
- `LineIndex.slice_span(start, end)` MUST preserve original line/column boundaries.

### 8.3 SourceSpan

```python
@dataclass(frozen=True, slots=True)
class SourceSpan:
    path: PurePosixPath
    start: int
    end: int
    line: int
    col: int
    end_line: int
    end_col: int
    cell: int | None = None
    cell_line: int | None = None
```

Rules:

- `start <= end`.
- `line`, `col`, `end_line`, and `end_col` are one-based.
- `cell` is zero-based notebook cell index.
- `cell_line` is one-based line inside the notebook markdown cell.
- For synthetic spans, use the nearest enclosing source span and set detail text accordingly.

### 8.4 MathBlock

```python
@dataclass(frozen=True, slots=True)
class MathBlock:
    document: SourceDocument
    raw: str
    normalized: str
    span: SourceSpan
    syntax: MathSyntax
    container: MathContainer
    block_id: str
```

`raw` is the original math payload without delimiters where possible. `normalized` is scanner-level cleanup only. Parser-level normalization belongs in `parse.normalize`.

```python
class MathSyntax(Enum):
    TEX = "tex"
    PLAIN = "plain"
```

```python
class MathContainer(Enum):
    MARKDOWN_DISPLAY = "markdown_display"
    MARKDOWN_INLINE = "markdown_inline"
    MARKDOWN_FENCE = "markdown_fence"
    LATEX_EQUATION = "latex_equation"
    LATEX_ALIGN_ROW = "latex_align_row"
    LATEX_DISPLAY = "latex_display"
    NOTEBOOK_MARKDOWN = "notebook_markdown"
```

`block_id` MUST be deterministic. Suggested format:

```text
{display_path}:{line}:{col}:{container}
```

### 8.5 Labels and references

```python
class LabelSource(Enum):
    LATEX_LABEL = "latex_label"
    MARKDOWN_ANCHOR = "markdown_anchor"
    MYST_DOLLAR_LABEL = "myst_dollar_label"
    MYST_DIRECTIVE_LABEL = "myst_directive_label"
    TEX_LABEL_IN_MARKDOWN_MATH = "tex_label_in_markdown_math"
    UNKNOWN = "unknown"

class ReferenceSource(Enum):
    LATEX_REF = "latex_ref"
    LATEX_EQREF = "latex_eqref"
    MARKDOWN_ANCHOR = "markdown_anchor"
    MYST_EQ_ROLE = "myst_eq_role"
    MYST_NUMREF_ROLE = "myst_numref_role"
    UNKNOWN = "unknown"
```

```python
@dataclass(frozen=True, slots=True)
class EquationLabel:
    label: str
    span: SourceSpan
    block_id: str | None = None
    source: LabelSource = LabelSource.UNKNOWN
```

```python
@dataclass(frozen=True, slots=True)
class EquationReference:
    target: str
    span: SourceSpan
    raw: str
    source: ReferenceSource
```

Rules:

- `label` and `target` MUST be normalized deterministically.
- For Markdown links, `#eq-energy` normalizes to `eq-energy`.
- For MyST roles such as ``{numref}`Eq. %s <energy>` ``, scanner MUST extract `energy` and preserve raw role text.
- Duplicate labels and missing references are check-level diagnostics, not scanner diagnostics.
- Notebook labels and references MUST preserve `cell` and `cell_line` once notebooks ship.

### 8.6 Diagnostic

```python
@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: Severity
    message: str
    span: SourceSpan | None
    equation: str | None = None
    detail: str | None = None
    hint: str | None = None
    rule: str | None = None
    suppressed: bool = False
```

```python
class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
```

Rules:

- `message` MUST be one sentence without trailing period.
- `detail` MAY contain computed facts such as dimensions or residuals.
- `hint` MAY contain one actionable fix.
- `code` MUST exist in `diag.catalog`.
- Suppressed diagnostics MUST appear in JSON when `--show-suppressed` is enabled.

### 8.7 CheckResult

```python
@dataclass(frozen=True, slots=True)
class CheckResult:
    diagnostics: tuple[Diagnostic, ...]
    files_checked: int
    math_blocks_checked: int
    config_path: PurePosixPath | None
    version: str
```

Exit code rule:

```python
def exit_code(self) -> int:
    if any(d.severity == ERROR and not d.suppressed for d in diagnostics):
        return 1
    return 0
```

CLI invalid usage, invalid config, internal error, unreadable explicit file, and reporter failure use exit code 2.

### 8.8 Stable sort

Diagnostics MUST be sorted by:

1. path,
2. cell, treating `None` before numbers,
3. line,
4. col,
5. code,
6. message.

This sort MUST be used before all reporters.

---

## 9. Scanner contracts

Every scanner implements:

```python
class Scanner(Protocol):
    def scan(self, document: SourceDocument, config: Config) -> ScanResult: ...
```

```python
@dataclass(frozen=True, slots=True)
class ScanResult:
    blocks: tuple[MathBlock, ...]
    labels: tuple[EquationLabel, ...] = ()
    references: tuple[EquationReference, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
```

Scanners MUST NOT parse math expressions. They extract math text, labels, references, and spans.

Scanners MUST preserve source locations enough for local output, GitHub annotations, JSON, and SARIF.

Scanners MUST NOT emit algebra, dimension, duplicate-label, or missing-reference diagnostics.

---

## 10. Parser and AST

Parser input is `MathBlock.normalized`.

Parser output is either:

```python
ParseOk(ast: EquationGroup)
```

or:

```python
ParseUnknown(reason: UnsupportedReason, diagnostics: tuple[Diagnostic, ...])
```

Parser MUST NOT run algebra, dimension, or reference checks.

Parser MUST NOT call SymPy directly. SymPy conversion belongs in `check.algebra`.

### AST nodes

All AST nodes MUST be frozen dataclasses with slots and spans.

```python
class Expr: ...

@dataclass(frozen=True, slots=True)
class EquationGroup:
    equations: tuple[Equation, ...]
    span: SourceSpan

@dataclass(frozen=True, slots=True)
class Equation:
    sides: tuple[Expr, ...]
    span: SourceSpan
```

`Equation.sides` supports chained equality. Checkers treat `a = b = c` as adjacent pairs: `a = b`, then `b = c`.

Expression nodes:

```python
@dataclass(frozen=True, slots=True)
class Number(Expr):
    value: Fraction
    raw: str
    span: SourceSpan

@dataclass(frozen=True, slots=True)
class Symbol(Expr):
    name: str
    raw: str
    span: SourceSpan

@dataclass(frozen=True, slots=True)
class UnaryOp(Expr):
    op: UnaryOperator
    operand: Expr
    span: SourceSpan

@dataclass(frozen=True, slots=True)
class BinaryOp(Expr):
    op: BinaryOperator
    left: Expr
    right: Expr
    span: SourceSpan

@dataclass(frozen=True, slots=True)
class FunctionCall(Expr):
    func: FunctionName
    arg: Expr
    span: SourceSpan
```

Operators:

```python
class BinaryOperator(Enum):
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    DIV = "div"
    POW = "pow"

class UnaryOperator(Enum):
    POS = "pos"
    NEG = "neg"

class FunctionName(Enum):
    SQRT = "sqrt"
```

### Parser diagnostics

| Code | Release | Default | Meaning |
|---|---:|---:|---|
| `PARSE001` | v0.1.0 | warning | Could not parse supported-looking math |
| `PARSE020` | v0.1.0 | info | Unsupported syntax; check skipped |
| `PARSE021` | v0.1.0 | info | Unsupported function; check skipped |
| `PARSE022` | v0.1.0 | info | Unsupported operator; check skipped |

`PARSE001` should be rare. Common unsupported constructs should have specific `PARSE02x` codes.

---

## 11. Algebra check

Algebra check proves or rejects scalar equalities for supported expressions.

The check MUST be exact. It MUST NOT use random sampling or floating-point testing.

v0.1.0 uses SymPy through a constrained adapter.

### Boundary

`check.algebra` owns:

- AST to SymPy conversion,
- symbol creation,
- equality normalization,
- residual computation,
- diagnostic detail formatting.

It MUST NOT expose SymPy objects outside `check.algebra`.

It MUST construct SymPy expressions from SciEqLint AST nodes only. It MUST NOT pass document text, normalized TeX strings, or user-controlled expressions to `sympy.parsing.sympy_parser.parse_expr`, `sympy.parsing.latex.parse_latex`, or equivalent text parsers.

### Diagnostics

| Code | Release | Default | Meaning |
|---|---:|---:|---|
| `ALG001` | v0.1.0 | error | Algebraic identity does not hold |
| `ALG010` | v0.1.0 | warning | Identity assumes nonzero denominator |
| `ALG020` | v0.1.0 | info | Algebra check skipped |
| `ALG030` | v0.1.0 | warning | Algebra check exceeded configured limit |

`ALG001` detail MUST include residual when printable:

```text
left - right = 2*a*b
```

If residual is too large:

```text
left - right is nonzero; residual omitted because it exceeds display limit
```

---

## 12. Dimension check

Dimension checking starts in v0.1.2.

Dimension checking MUST be useful when configured and quiet when unconfigured.

### Dimension model

Use integer vectors over SI base dimensions:

```text
(M, L, T, I, Theta, N, J)
```

```python
@dataclass(frozen=True, slots=True)
class DimVector:
    exponents: tuple[int, int, int, int, int, int, int]
```

Config accepts `Theta` for temperature. Unicode `Θ` MAY be accepted as an alias in v0.2.0.

Dimensionless is all zeros.

### Dimension expression syntax

```toml
[vars]
m = "M"
x = "L"
t = "T"
v = "L T^-1"
a = "L T^-2"
F = "M L T^-2"
E = "M L^2 T^-2"
theta = "1"
```

Rules:

- whitespace separates factors,
- power syntax is `L^2`, `T^-1`,
- `1` means dimensionless,
- unknown base dimension names are config errors.

### Dimension diagnostics

| Code | Release | Default | Meaning |
|---|---:|---:|---|
| `DIM001` | v0.1.2 | error | Equation sides have different dimensions |
| `DIM002` | v0.1.2 | error | Addition/subtraction combines incompatible dimensions |
| `DIM003` | v0.2.0 if functions ship | error | Function argument must be dimensionless |
| `DIM010` | v0.1.2 | warning | Unknown variable dimension |
| `DIM020` | v0.1.2 | info | Dimension check skipped |
| `CFG010` | v0.1.2 | error | Invalid dimension expression |
| `CFG011` | v0.2.0 | error | Alias collision |

---

## 13. References, symbols, and graph

References are core v0.1.0. Graph and symbols come later.

### Reference diagnostics

| Code | Release | Default | Meaning |
|---|---:|---:|---|
| `REF001` | v0.1.0 | error | Duplicate equation label |
| `REF002` | v0.1.0 | warning | Missing equation reference target |
| `REF003` | v0.1.0 | info | Equation block has no label in strict mode |

Rules:

- Duplicate labels emit `REF001`.
- Missing supported reference targets emit `REF002`.
- Strict mode MAY emit `REF003`.
- Reference checking MUST be deterministic and zero-config.
- Natural-language references are not extracted in v0.x.

### Graph export

Graph export starts in v0.3.0.

Graph schema example:

```json
{
  "schema_version": "0.3",
  "nodes": [
    {"id": "eq:energy", "kind": "equation", "path": "paper.tex", "line": 42}
  ],
  "edges": [
    {"from": "eq:work", "to": "eq:force", "kind": "references"}
  ]
}
```

### Symbol table

Symbol checks start in v0.4.0 and MUST be explicit. No prose inference in v0.x.

---

## 14. Diagnostics and reporters

Diagnostic codes are stable API once introduced.

### Initial diagnostic catalog by v0.1.0

| Code | Default | Meaning |
|---|---:|---|
| `ALG001` | error | Algebraic identity does not hold |
| `ALG010` | warning | Identity assumes nonzero denominator |
| `ALG020` | info | Algebra check skipped |
| `ALG030` | warning | Algebra check exceeded configured limit |
| `PARSE001` | warning | Could not parse supported-looking math |
| `PARSE020` | info | Unsupported syntax; check skipped |
| `PARSE021` | info | Unsupported function; check skipped |
| `PARSE022` | info | Unsupported operator; check skipped |
| `SCAN001` | warning | Unterminated math container |
| `SCAN002` | info | Inline math skipped by config |
| `INP001` | error | File could not be read or decoded |
| `INP003` | warning | File exceeded configured limit |
| `CFG001` | error | Invalid config file |
| `REF001` | error | Duplicate equation label |
| `REF002` | warning | Missing equation reference target |
| `REF003` | info | Missing equation label in strict mode |

Later codes are added only when their release starts.

### Severity override

Config MAY override severity for selected codes:

```toml
[severity]
DIM010 = "info"
PARSE020 = "ignore"
```

Valid levels:

- `error`,
- `warning`,
- `info`,
- `ignore`.

Ignored diagnostics do not appear except when `--show-ignored` exists and is enabled.

### JSON reporter

Schema v0.1:

```json
{
  "schema_version": "0.1",
  "tool": "scieqlint",
  "version": "0.1.0",
  "summary": {
    "files_checked": 1,
    "math_blocks_checked": 2,
    "errors": 1,
    "warnings": 0,
    "info": 0
  },
  "diagnostics": [
    {
      "code": "ALG001",
      "severity": "error",
      "message": "algebraic identity does not hold",
      "path": "examples/bad/famous_bad.md",
      "line": 5,
      "col": 1,
      "end_line": 5,
      "end_col": 29,
      "cell": null,
      "cell_line": null,
      "equation": "(a+b)^2 = a^2 + b^2",
      "detail": "left - right = 2*a*b",
      "hint": null,
      "suppressed": false
    }
  ]
}
```

Rules:

- Include all keys even when value is null.
- No timestamps.
- No absolute paths unless `--absolute-paths`.
- No color or ANSI codes.
- JSON output MUST validate against checked-in schema artifacts in tests.

### Reporter interface

```python
class Reporter(Protocol):
    def render(self, result: CheckResult) -> str: ...
```

Reporters MUST NOT mutate diagnostics.
Reporters MUST NOT read files.
Reporters MUST NOT run checks.

---

## 15. Config

Default config path:

```text
scieqlint.toml
```

Search order:

1. Explicit `--config` path.
2. Current working directory.
3. Parent directories until no more parents remain.
4. Built-in defaults.

Config loading MUST be deterministic.

The v0.1.5 loader does not detect VCS roots. Users that need a specific project
boundary SHOULD pass `--config`.

### Planned config schema

```toml
[project]
root = "."
order = []

[scanner]
markdown = true
inline_math = false
math_fences = true

[parser]
unknown_identifier_policy = "single_symbol"

[checks.algebra]
enabled = true
unknown = "info"
denominator_warnings = true

[checks.references]
enabled = true
missing = "warn"
duplicate_labels = "error"
missing_label_strict = false

[limits]
max_file_bytes = 1048576
max_math_blocks_per_file = 2000
max_expression_nodes = 2000
algebra_max_ops = 2000
algebra_timeout_ms = 250
max_reported_diagnostics_per_file = 200

[report]
absolute_paths = false
color = "auto"

[severity]
# PARSE020 = "ignore"

[ignore]
files = ["build/**", "dist/**", ".venv/**"]
```

The v0.1.5 loader applies only the implemented subset of this schema:
`[scanner].markdown`, `[scanner].inline_math`, `[scanner].math_fences`,
`[checks.algebra].enabled`, `[checks.references].enabled`,
`[checks.references].missing_label_strict`, `[checks.dimension].mode`,
`[checks.dimension].unknown_variables`, `[vars]`, and `[ignore].files`.
Other tables and keys are reserved specification surface.

v0.1.2 adds:

```toml
[checks.dimension]
mode = "auto"
unknown_variables = "warn"

[vars]
# symbol = "dimension"
```

v0.2.0 adds:

```toml
[aliases]
# rho = ["\\rho", "ρ"]

[report]
show_suppressed = false
show_ignored = false
```

### Validation

Invalid config is exit code 2.

Validation MUST report all detected config errors at once where practical.

Examples:

- invalid TOML,
- unknown check name,
- unknown severity,
- negative limit,
- invalid dimension expression once dimensions ship,
- alias collision once aliases ship.

Do not add Pydantic for v0.1.0 unless validation complexity becomes high.

---

## 16. CLI and integrations

### v0.1.0 CLI

```bash
scieqlint check [PATH_OR_GLOB...]
scieqlint init
scieqlint demo
scieqlint explain CODE
```

Exit codes:

- `0`: no unsuppressed errors,
- `1`: unsuppressed errors found,
- `2`: invalid usage, invalid config, explicit-file IO failure, internal error, reporter failure.

### v0.1.1 pre-commit

`.pre-commit-hooks.yaml`:

```yaml
- id: scieqlint
  name: SciEqLint
  description: Check equations and equation references in supported scientific documents.
  entry: scieqlint check
  language: python
  files: '\.(md|markdown)$'
  require_serial: true
```

v0.1.1 hook metadata MUST target only `.md` and `.markdown`. v0.1.3 expands the pattern to include `.tex`; v0.1.4 expands it to include `.ipynb`.

### v0.1.5 SARIF workflow

```yaml
permissions:
  contents: read
  security-events: write

steps:
  - uses: actions/checkout@v6
  - uses: actions/setup-python@v6
    with:
      python-version: "3.11"
  - run: python -m pip install scieqlint==0.1.5
  - run: scieqlint check "docs/**/*.md" "docs/**/*.ipynb" --format sarif --output scieqlint.sarif
  - uses: github/codeql-action/upload-sarif@v4
    with:
      sarif_file: scieqlint.sarif
      category: scieqlint-docs
```

SARIF is a reporter. It MUST NOT change analysis.

---

## 17. Testing

### v0.1.0 test modules

```text
tests/test_source.py
tests/test_markdown_scan.py
tests/test_myst_scan.py
tests/test_parser.py
tests/test_ast_print.py
tests/test_algebra.py
tests/test_references.py
tests/test_config.py
tests/test_report_text.py
tests/test_report_json.py
tests/test_json_schema.py
tests/test_package_resources.py
tests/test_api.py
tests/test_cli.py
```

Add later:

```text
tests/test_dimensions.py        # v0.1.2
tests/test_latex_scan.py        # v0.1.3
tests/test_notebook_scan.py     # v0.1.4
tests/test_report_github.py     # v0.1.1
tests/test_report_sarif.py      # v0.1.5
tests/test_suppressions.py      # v0.2.0
tests/test_graph.py             # v0.3.0
tests/test_symbols.py           # v0.4.0
```

### Golden tests

v0.1.0 fixtures:

```text
tests/fixtures/bad/famous_bad.md
tests/fixtures/good/algebra_good.md
tests/fixtures/bad/references_bad.md
tests/fixtures/good/references_good.md
tests/fixtures/good/myst_good.md
tests/fixtures/bad/myst_bad.md
```

v0.1.0 golden outputs:

```text
tests/golden/text/*.txt
tests/golden/json/*.json
```

Later golden outputs:

```text
tests/golden/github/*.txt       # v0.1.1
tests/golden/sarif/*.json       # v0.1.5
```

Golden tests MUST be stable across operating systems.

### Accuracy benchmark fixtures

v0.1.0 includes a small deterministic accuracy benchmark set:

```text
benchmarks/accuracy/
  algebra.yml
  references.yml
  parse_unknown.yml
```

v0.1.2 adds:

```text
benchmarks/accuracy/dimensions.yml
```

Rules:

- Each benchmark case has input, config if needed, expected diagnostic codes, and expected pass/fail status.
- Benchmarks MUST run in PR CI as ordinary fast tests.
- Release notes SHOULD report benchmark count and changed expectations.
- Benchmark cases MUST be small and license-safe.

### Coverage gates

v0.1.0 gates:

- overall coverage >= 85%,
- `check.references` >= 95%,
- `report.json` >= 95%.

v0.1.1 adds:

- `report.github` >= 95%.

v0.1.2 adds:

- `check.dimensions` >= 95%.

Coverage exceptions require an explicit comment in coverage config.

---

## 18. CI and release process

### Required PR gate by v0.1.0

Required on every PR touching code, tests, docs, config, or templates:

- Ruff format check.
- Ruff lint.
- Pyright.
- import-linter.
- pytest with coverage.
- wheel build and install smoke test.
- docs build if docs exist.
- self-check on clean examples.

Required jobs use `ubuntu-latest` and Python 3.11. Compatibility matrix runs separately.

### Required workflow jobs

File: `.github/workflows/ci.yml`

Jobs:

1. `quality`
2. `test`
3. `package`
4. `docs`
5. `self-check`

Workflow-level permissions:

```yaml
permissions:
  contents: read
```

Recommended commands:

```bash
uv sync --locked --group dev
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run lint-imports
uv run pytest --cov=scieqlint --cov-report=term-missing
uv build
uv run twine check dist/*
uv run mkdocs build --strict
uv run scieqlint check "examples/good/**/*.md" --format text
```

### Release step package template

Every release follows this sequence:

1. Scope lock: update release checklist.
2. Data contracts: update models, diagnostics, and schemas first.
3. Core implementation: scanner/parser/checker/reporter changes in separate PRs.
4. Golden fixtures: add good/bad examples and exact output expectations.
5. Docs: update quickstart, limitations, diagnostics, and integration pages.
6. Package smoke: build wheel, install in a clean venv, run CLI smoke.
7. Release candidate: tag rc or create a pre-release branch.
8. Final tag: publish only after release checks pass.

A feature is not shipped until docs and fixtures demonstrate it. This rule applies even to small reporter, config, and scanner changes.

### Release checklist

Every release MUST include:

- release scope statement,
- release checklist status,
- changelog entry,
- version bump,
- docs update,
- diagnostic catalog update when needed,
- JSON/SARIF schema update when needed,
- accuracy benchmark update when expectations change,
- golden test update when output changes,
- wheel install smoke test,
- package-data verification,
- release notes with migration notes.

Release notes MUST use:

```text
Added
Changed
Fixed
Deprecated
Removed
Migration notes
Known limitations
```

No vague release notes such as “various improvements.”

---

## 19. Security and performance

### Runtime security

The checker runtime MUST NOT:

- make network calls,
- execute notebooks,
- import user project modules,
- evaluate Python code from documents,
- run shell commands from analysis core,
- write files except explicit `--output` or `init`,
- follow symlinks outside project root by default,
- read ignored files unless explicitly passed,
- call SymPy text parsers on document content,
- execute Sphinx, Jupyter Book, Pandoc, LaTeXML, ChkTeX, latexindent, or editor tooling from core analysis.

### Source limits

Defaults:

```toml
[limits]
max_file_bytes = 1048576
max_math_blocks_per_file = 2000
max_expression_nodes = 2000
max_reported_diagnostics_per_file = 200
```

Files over limit emit `INP003` warning and are skipped unless config explicitly allows.

### Determinism

Output MUST NOT depend on:

- filesystem traversal order,
- dictionary insertion from external sources,
- locale,
- timezone,
- wall-clock time,
- random seeds,
- absolute temp paths.

Sort all user-visible lists.

### v0.1.0 performance target

On GitHub Ubuntu runner:

| Case | Budget |
|---|---:|
| 100 Markdown files, 500 equations, 500 references | <3s |
| 1 large Markdown document, 300 equations, 300 references | <2s |
| JSON report with 1000 diagnostics | <1s reporter time |
| Cold CLI startup | <1s max |

Performance tests are non-required until v0.4.0, then scheduled.

---

## 20. Docs and governance

### README first screen

README MUST show:

1. Project name and one-line pitch.
2. Install command.
3. `scieqlint check .` zero-config workflow.
4. One algebra error demo.
5. One broken-reference demo.
6. Link to limitations.
7. GitHub Actions snippet once v0.1.1 ships.
8. Dimension demo once v0.1.2 ships.

No architecture wall on the first screen.

### Limitations page

Limitations are a trust asset.

Must include:

- supported grammar table,
- supported label/reference forms,
- supported MyST subset,
- unsupported MyST/Sphinx/Jupyter Book behavior,
- unsupported examples,
- what unknown means,
- why dimensions are quiet without config,
- why notebooks are not executed,
- why unsupported math is not guessed,
- why SciEqLint does not replace ChkTeX, latexindent, TexLab, Sphinx, or Jupyter Book.

### Diagnostic docs

Every diagnostic code page/table MUST include:

- code,
- default severity,
- meaning,
- example input,
- example output,
- config knobs.


### OSS contributor experience

Contributor experience is part of product quality. SciEqLint should feel approachable to a stranger who has never touched the repository, while still protecting the trust rules that make the project credible.

The contributor promise:

- a new contributor can understand the first useful product win in less than five minutes,
- a new contributor can run the full local quality loop with one documented command group,
- a new contributor can find a starter issue with a clear summary, affected area, change, and test notes,
- a reviewer can reject scope creep by linking to this spec instead of debating taste,
- a contributor never has to infer whether a change belongs to scanner, parser, checker, reporter, config, docs, or packaging,
- a contributor never has to guess whether a feature belongs in the current release.

By v0.0.1 the repository MUST include these top-level files:

| File | Purpose | Required by |
|---|---|---:|
| `README.md` | product pitch, install, first demo, limitations link | v0.0.1 |
| `CONTRIBUTING.md` | local setup, test commands, PR expectations, issue labels | v0.0.1 |
| `ROADMAP.md` | release ladder rewritten for contributors | v0.0.1 |
| `GOOD_FIRST_ISSUES.md` | ten starter issues | v0.0.1 |
| `CODE_OF_CONDUCT.md` | behavior rules for safe collaboration | v0.0.1 |
| `SECURITY.md` | responsible disclosure and security boundaries | v0.0.1 |
| `SUPPORT.md` | where to ask questions and what is out of support | v0.0.1 |
| `MAINTAINERS.md` | review expectations and decision process | v0.0.1 |
| `.github/PULL_REQUEST_TEMPLATE.md` | contributor checklist | v0.0.1 |
| `.github/ISSUE_TEMPLATE/*.md` | bug, feature, docs, and task issue templates | v0.0.1 |

The first screen of `CONTRIBUTING.md` MUST include:

```bash
git clone https://github.com/OWNER/scieqlint.git
cd scieqlint
uv sync --group dev
uv run pytest
uv run ruff format --check .
uv run ruff check .
uv run pyright
```

If `uv` is not installed, the file SHOULD link or point to the supported fallback command sequence using standard Python virtual environments. The fallback MUST remain a documented second path, not the primary path.

#### Contributor issue contract

Every starter or help-wanted issue MUST include:

- summary,
- release target,
- scope label: `required`, `cuttable`, or `forbidden-for-now`,
- affected area,
- requested change,
- test notes when applicable,
- reviewer note when useful.

Good issue template:

```md
## Summary

## Affected Area

```text
Release:
Area:
Scope:
```

## Change

## Test Notes
```

A `good first issue` MUST be solvable without making product policy decisions. It SHOULD be less than roughly 150 lines of code or docs, excluding fixtures and golden outputs. It MUST NOT require changing public JSON schema, grammar semantics, algebra behavior, release policy, or security rules unless the issue is explicitly marked `good second issue` instead.

A `good second issue` MAY touch code behavior but MUST still stay narrow and name a reviewer area.

#### Label taxonomy

The repository MUST define labels before the first public call for contributors.

Required contributor labels:

| Label | Meaning |
|---|---|
| `good first issue` | safe for a new contributor; no product judgment required |
| `good second issue` | small behavior change after one successful PR |
| `help wanted` | maintainers want outside help and will review it |
| `needs design` | not ready for implementation |
| `blocked` | waiting on another issue or release |
| `needs fixture` | needs example input/output coverage |
| `needs docs` | needs documentation work |
| `mentor available` | maintainer can give extra guidance |

Required area labels:

```text
area:cli
area:config
area:docs
area:scanner-markdown
area:scanner-latex
area:scanner-notebook
area:parser
area:algebra
area:references
area:dimensions
area:report-text
area:report-json
area:report-github
area:report-sarif
area:packaging
area:tests
area:security
```

Required release labels:

```text
release:v0.0.1
release:v0.1.0
release:v0.1.1
release:v0.1.2
release:v0.1.3
release:v0.1.4
release:v0.1.5
release:v0.2.0
future
```

Required scope labels:

```text
scope:required
scope:cuttable
scope:forbidden-for-now
```

Issues marked `scope:forbidden-for-now` MUST be closed or converted to a discussion unless they document a future release idea. They MUST NOT remain in the active milestone.

#### First ten starter issues

By v0.0.1, `GOOD_FIRST_ISSUES.md` MUST include at least these ten issues, even if the tracker is not yet public:

| # | Title | Labels | Contributor value |
|---:|---|---|---|
| 1 | Add minimal CLI help golden snapshots | `good first issue`, `area:cli`, `release:v0.0.1` | teaches CLI shape without touching analysis |
| 2 | Implement or test `LineIndex` offset mapping | `good second issue`, `area:tests`, `release:v0.1.0` | teaches source spans, a core project concept |
| 3 | Add diagnostic catalog table tests | `good first issue`, `area:tests`, `release:v0.1.0` | teaches stable diagnostic codes |
| 4 | Add Markdown display-math scanner fixtures | `good first issue`, `area:scanner-markdown`, `release:v0.1.0` | teaches scanner contracts |
| 5 | Add MyST directive label fixtures | `good first issue`, `area:scanner-markdown`, `release:v0.1.0` | teaches MyST support boundaries |
| 6 | Add parser tests for unary signs and powers | `good second issue`, `area:parser`, `release:v0.1.0` | teaches grammar without expanding scope |
| 7 | Add algebra golden case for famous false identity | `good first issue`, `area:algebra`, `release:v0.1.0` | anchors the product demo |
| 8 | Add JSON reporter schema validation fixture | `good second issue`, `area:report-json`, `release:v0.1.0` | teaches automation contract |
| 9 | Write limitations examples for unsupported functions | `good first issue`, `area:docs`, `release:v0.1.0` | reinforces anti-overclaiming |
| 10 | Add package-resource smoke test for grammar and schemas | `good second issue`, `area:packaging`, `release:v0.1.0` | protects release quality |

These are seed issues. Maintainers MAY replace them with equivalent issues, but the issue list MUST preserve the same mix: docs, fixtures, tests, CLI, scanner, parser, reporter, packaging.

#### Contributor paths

The repository SHOULD document four contributor paths:

| Path | Best first contribution | Avoid at first |
|---|---|---|
| Scientific writer | limitations examples, fixture cases, README clarity | parser grammar changes |
| Python developer | tests, CLI, config validation, reporter output | algebra semantics |
| Math/science domain contributor | benchmark cases, unsupported examples, dimension configs | broad symbolic claims |
| CI/integration contributor | package smoke, pre-commit, GitHub reporter, SARIF fixtures | core checker behavior |

Each path SHOULD have one linked starter issue.

#### PR flow

Pull requests MUST use the template and identify the layer touched:

```text
Layer: scanner / parser / checker / reporter-schema / config / docs / packaging-CI
Release target: v0.1.0 / v0.1.1 / future
Scope: required / cuttable / forbidden-for-now
Behavior change: yes/no
Golden output changed: yes/no
Docs updated: yes/no
```

A PR marked `behavior change: yes` MUST include tests. A PR marked `golden output changed: yes` MUST explain why the output changed.

Maintainers SHOULD review PRs for scope first, correctness second, and style last. Review comments SHOULD distinguish blocking requests from suggestions.

#### Maintainer response expectations

Maintainers SHOULD triage new issues with labels before deep discussion. A triaged issue has at least one area label, one release or `future` label, and one status label.

Maintainers SHOULD avoid asking contributors to expand the PR beyond the stated issue. When a PR reveals adjacent work, maintainers SHOULD ask for a follow-up issue instead of widening the PR.

Maintainers MUST NOT merge drive-by broadening of parser, algebra, scanner, or reporter semantics unless the change is already in the release scope.

#### Review style

Reviews SHOULD be direct, kind, and specific. Preferred review wording:

```text
Blocking: this changes parser scope, which belongs to v0.2. Please remove it from this PR.
Non-blocking: this helper name could be clearer, but it does not need to block merge.
Question: did you consider adding this as a golden fixture instead of only a unit test?
```

Reviewers SHOULD explain project-specific constraints rather than saying only “no.” The best rejection links to one of: release ladder, trust rules, parser scope, reporter contract, or limitations page.

#### Documentation for contributors

The docs site SHOULD include a `Contributing` section with these pages by v0.1.0:

```text
docs/contributing/index.md
docs/contributing/dev-setup.md
docs/contributing/architecture-map.md
docs/contributing/pr-dependency-checks.md
docs/contributing/testing.md
docs/contributing/golden-files.md
docs/contributing/diagnostics.md
docs/contributing/release-scope.md
docs/contributing/review-guide.md
docs/contributing/issue-guide.md
```

The architecture map MUST be short and task-oriented. It SHOULD answer:

- “I want to add a fixture; where do I go?”
- “I want to add a diagnostic; what files change?”
- “I want to change JSON output; what contract must I preserve?”
- “I want to support a new math syntax; why is that probably not a starter PR?”

#### Contributor acceptance by release

v0.0.1 contributor acceptance:

- top-level contributor files exist,
- issue and PR templates exist,
- at least ten starter issues are written,
- labels are documented,
- local setup commands are documented and tested by a maintainer from a clean checkout.

v0.1.0 contributor acceptance:

- contributor docs explain fixtures, golden outputs, diagnostics, and release scope,
- at least five starter issues remain open and current after v0.1.0 ships,
- at least one example PR in docs shows the smallest acceptable contribution path,
- release notes thank external contributors if any contributed.

v0.2.0 contributor acceptance:

- docs explain how to add a preset safely,
- docs explain how suppressions are tested,
- at least one `good second issue` exists for aliases or presets if those features ship.


### Contribution rules

PRs MUST be narrow.

One PR should not combine:

- scanner change,
- parser grammar change,
- algebra behavior change,
- reporter schema change,
- docs redesign.

Any diagnostic behavior change requires:

- tests,
- docs update,
- changelog entry if user-visible.

Any grammar expansion requires:

- parser tests,
- algebra/dimension behavior tests,
- unsupported regression tests,
- limitations update.

---

## 21. Release checks by release

### v0.0.1 checks

- Wheel builds.
- Wheel installs in clean venv.
- `scieqlint` console script works.
- `python -m scieqlint` works.
- `py.typed` included.
- CLI commands exist.
- CI skeleton is green.
- Contributor quickstart can be followed on a clean machine.
- At least ten starter issues are written using the required issue contract.

### v0.1.0 checks

Product:

- README first screen shows install, `scieqlint check .`, algebra demo, broken-reference demo, and limitations link.
- `scieqlint demo` works without input files.
- `scieqlint check .` provides useful zero-config diagnostics on Markdown/MyST files.
- Limitations page clearly states unsupported syntax, supported reference forms, supported MyST subset, and unsupported build behavior.
- Contributor docs explain how to add a scanner fixture, parser case, diagnostic, reporter golden, and limitation entry without changing unrelated layers.
- The issue tracker contains labeled `good first issue`, `help wanted`, `area:*`, `release:*`, and `scope:*` examples aligned with v0.1.0.

CLI:

```bash
scieqlint check examples/bad/famous_bad.md
scieqlint check examples/bad/famous_bad.md --format json
scieqlint check examples/bad/references_bad.md
scieqlint init
scieqlint demo
scieqlint explain ALG001
scieqlint explain REF002
python -m scieqlint check examples/bad/famous_bad.md
```

Exit codes:

- wrong equation -> 1,
- clean file -> 0,
- invalid config -> 2,
- missing reference warning-only result -> 0 unless severity override escalates it.

Scanners:

- Markdown display math extracted with correct line/col.
- Markdown equation labels and anchor references extracted.
- MyST math directive labels, dollar-math suffix labels, TeX labels inside Markdown math, `{eq}` roles, and `{numref}` roles extracted.
- Unterminated math container produces scanner warning, not crash.

References:

- Duplicate Markdown labels emit `REF001`.
- Missing Markdown/MyST references emit `REF002`.
- Reference diagnostics have stable source spans.
- Reference checks work with no config file.

Parser:

- Supported minimal grammar parses.
- Unsupported syntax returns unknown diagnostic, not crash.
- Chained equality creates adjacent checks.
- `\sin`, `\cos`, `\log`, and `\exp` emit `PARSE021`.

Algebra:

- Correct polynomial identities pass.
- Incorrect polynomial identities emit `ALG001`.
- Trig identity is unsupported at parser level.

Reporters:

- Text output stable.
- JSON schema stable, timestamp-free, and validated.
- JSON output is suitable for single-file editor-style integration.

Benchmarks:

- Initial accuracy benchmark fixtures exist for algebra, references, and parse-unknown cases.
- Benchmark expectations are deterministic and run in PR CI.

Package:

- Wheel installs in clean venv.
- Package includes grammar, schemas, `py.typed`, and demo examples as needed.
- Package resources load through `importlib.resources`.

### v0.1.1 acceptance

- GitHub reporter output matches workflow command escaping.
- `--format github` emits annotations with file, line, col, and title.
- pre-commit metadata validates.
- README includes copy-paste GitHub annotation workflow.
- No analysis behavior changes.

### v0.1.2 acceptance

- Zero-config mode emits no `DIM010` noise.
- `F = m*a` passes under mechanics config.
- `E = m*c` emits `DIM001` under mechanics config.
- `E = m*c^2` passes.
- `x + t` emits `DIM002` when dimensions are configured.
- Unknown variable policy works when dimension checking is active.
- Dimension benchmark fixtures exist.

### v0.1.3 acceptance

- LaTeX equation and align environments extracted.
- LaTeX `\label`, `\ref`, and `\eqref` extracted.
- Duplicate labels and missing refs work across Markdown and LaTeX together.
- Unterminated math container warns, not crashes.

### v0.1.4 acceptance

- Notebook markdown cells scanned.
- Code cells ignored.
- Notebook markdown references preserve cell metadata.
- Malformed notebook behavior is deterministic.

### v0.1.5 acceptance

- SARIF reporter golden-tested.
- SARIF output includes SARIF 2.1.0 top-level fields, stable `ruleId`, repo-relative artifact URIs, physical locations, deterministic `partialFingerprints`, and rule metadata.
- SARIF result-size guard works deterministically.
- Sample workflow documents `security-events: write` and `category`.
- Composite GitHub Action wrapper is thin and documented.
- No new analysis behavior ships.

### v0.2.0 acceptance

- Suppression comments work for Markdown and LaTeX.
- Suppressed diagnostics do not fail CLI.
- Presets list/show/init works.
- Alias normalization works if included.
- Scalar functions parse only if explicitly included in the release scope.
- Jupyter Book guide tested manually.

### v0.3.0 acceptance

- Graph JSON schema is stable and documented.
- LaTeX labels appear as graph nodes.
- Markdown/MyST labels appear as graph nodes.
- Equation references appear as graph edges.
- Graph output is stable sorted.

### v0.4.0 acceptance

- Symbol directives parsed.
- Undefined symbol check works across ordered files.
- Redefinition dimension conflicts emit `SYM002`.
- Symbol feature can be disabled cleanly.
- No natural-language symbol inference.

### v1.0.0 acceptance

- Diagnostic catalog frozen.
- JSON schema frozen.
- SARIF schema stable.
- Config schema documented.
- Public API documented.
- Compatibility matrix green.
- Accuracy benchmark summary published.
- Performance budgets met.
- Security/release docs complete.
- At least 100 documented equation fixtures.

---

## 22. Final product rule

SciEqLint should feel boringly reliable. It should also feel unusually easy to contribute to without accidentally damaging that reliability.

A small exact checker that says “unknown” honestly is better than a broad checker that guesses. A narrow release that ships on time is better than a grand release that never earns trust.

The v11.1 path wins by making the first public release undeniable: install it, run it on Markdown/MyST docs, catch a wrong equation or broken reference, get deterministic output, and understand exactly what was checked.

---

## Appendix: Complete repository handoff pack

The companion ZIP includes `PACK_MANIFEST.md`, which lists every repository scaffold file. The pack is intentionally split into specification, governance, docs, CI, package scaffold, tests, schemas, examples, and release checklists.

The included code is a v0.1.5 analyzer slice. It exists so contributors can install,
run, test, and extend real equation and reference checks while preserving the
documented release boundaries.
