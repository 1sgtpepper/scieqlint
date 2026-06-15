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
generation pipelines, initialize the packaged profile and use the resulting
config with GitHub annotations:

```yaml
- name: Write generated MyST profile
  run: scieqlint init --preset generated-myst --path scieqlint.generated-myst.toml
- name: Check generated scientific docs
  run: scieqlint check "docs/**/*.md" --config scieqlint.generated-myst.toml --format github
```

The `generated-myst` preset uses current deterministic checks only: Markdown/MyST
math containers, inline math, algebra, equation references, duplicate labels, and
strict unsupported-math diagnostics. It does not judge OCR, translation, or prose
quality.

The reporter must escape workflow command payloads correctly and must not change analysis behavior.

v0.1.1 does not add scanner, parser, dimension, or algebra features.
