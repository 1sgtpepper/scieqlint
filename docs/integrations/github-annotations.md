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
generation pipelines, materialize the generated-document preset before using
GitHub annotations:

```yaml
- name: Check generated scientific docs
  run: scieqlint check "docs/**/*.md" --config scieqlint.generated-myst.toml --format github
```

Create `scieqlint.generated-myst.toml` once with
`scieqlint init --preset generated-myst --path scieqlint.generated-myst.toml` and
commit the file. The preset selects the generated-myst profile and supplies the
generated-document scanner/parser policy, including source-only `GEN002` checks.

The `generated-myst` preset uses deterministic checks only: Markdown/MyST math
containers, inline math, suspicious generated formula text, bracketed LaTeX blocks,
formula placeholders, algebra, equation references, duplicate
labels, and strict unsupported-math diagnostics. It does not judge OCR, translation,
or prose quality. Formula placeholders are reported as `GEN004`; they remain outside
`GEN002`.

The reporter must escape workflow command payloads correctly and must not change analysis behavior.

v0.1.1 does not add scanner, parser, dimension, or algebra features.
