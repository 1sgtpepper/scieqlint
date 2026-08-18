# GitHub annotations

GitHub annotations start in v0.1.1 with `--format github`.

Example:

```bash
scieqlint check examples/bad/famous_bad.md --format github
```

In GitHub Actions:

```yaml
- name: Check equations
  run: scieqlint check "docs/**/*.md" --format github
```

For generated Markdown/MyST output from translation, conversion, or document
generation pipelines, materialize the generated-document preset and append an
explicit `[profile]` selection before using GitHub annotations:

```yaml
- name: Check generated scientific docs
  run: scieqlint check "docs/**/*.md" --config scieqlint.generated-myst.toml --format github
```

Create `scieqlint.generated-myst.toml` once with
`scieqlint init --preset generated-myst --path scieqlint.generated-myst.toml`,
then append `[profile]` with `name = "generated-myst"` and commit the file. The
preset supplies scanner/parser defaults; the explicit profile enables
generated-output diagnostics.

The `generated-myst` profile uses current deterministic checks only:
Markdown/MyST math containers, inline math, algebra, equation references,
duplicate labels, and strict unsupported-math diagnostics. It does not judge OCR,
translation, or prose quality.

The reporter must escape workflow command payloads correctly and must not change analysis behavior.

v0.1.1 does not add scanner, parser, dimension, or algebra features.
