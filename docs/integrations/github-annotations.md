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
For notebook Markdown cells, GitHub output emits file-level annotations and puts
the cell-local line in the annotation message, because SciEqLint does not map
cell spans back to physical `.ipynb` JSON line numbers.

v0.1.1 does not add scanner, parser, dimension, or algebra features.
