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

The reporter must escape workflow command payloads correctly and must not change analysis behavior.

v0.1.1 does not add scanner, parser, dimension, or algebra features.
