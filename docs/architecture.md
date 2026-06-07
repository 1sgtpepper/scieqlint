# Architecture

SciEqLint uses a functional core with adapter shells.

```text
CLI / pre-commit / GitHub Action / editor
        |
        v
app service
        |
        v
file discovery -> source loading -> scanning -> parsing -> checks -> diagnostics -> reporting
```

## Layer rules

- Scanners extract math text, labels, references, and source spans. They do not parse expressions.
- Parser returns AST or unknown diagnostics. It does not call SymPy.
- Checkers own algebra, references, dimensions, symbols, and graph behavior.
- Reporters render diagnostics. They do not read files or run checks.
- CLI owns command-line plumbing only.

Import boundaries are enforced by import-linter no later than v0.1.0.
