# Architecture

SciEqLint uses a functional core with adapter shells.

The ratified architecture decision record is
[ADR R1-001: Deterministic Snapshot Kernel](architecture/deterministic-snapshot-kernel-adr.md).

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

- Frontends extract lexical math candidates, labels, references, and source spans. They do not
  assign final generated-formula kinds, classify AMS/unsupported math, or apply portability policy.
- MathHost owns final math classification, parser recovery, macro scope facts, and Typst math
  portability facts. It does not call SymPy.
- WorkspaceHost owns project-relative identity and caller-supplied membership/visibility projection.
- PolicyHost owns output-profile support policy and diagnostic severity selection.
- Checkers own algebra, references, dimensions, symbols, and graph behavior.
- Generated-output checks consume explicit source-to-generated provenance facts;
  the generated profile records the generated document plus caller-supplied source kind and conversion stage, and never infers missing origin metadata.
- Graph export models are built from scanner label/reference outputs and do not rescan documents.
- Reporters render diagnostics. They do not read files or run checks.
- CLI owns command-line plumbing only.

Import boundaries are enforced by import-linter no later than v0.1.0.

The reviewed R1 package boundary artifact is the
[module ownership map](architecture/module-ownership.md).
