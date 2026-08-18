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
generation pipelines, keep an explicit `[profile]` selection in the project
config and use it with GitHub annotations:

```yaml
- name: Check generated scientific docs
  run: scieqlint check "docs/**/*.md" --config scieqlint.toml --format github
```

The `generated-myst` profile uses current deterministic checks only:
Markdown/MyST math containers, inline math, algebra, equation references,
duplicate labels, and strict unsupported-math diagnostics. It does not judge OCR,
translation, or prose quality. The packaged preset supplies scanner/parser
defaults but does not select the profile.

The reporter must escape workflow command payloads correctly and must not change analysis behavior.

v0.1.1 does not add scanner, parser, dimension, or algebra features.
