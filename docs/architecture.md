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
  portability facts. It does not call SymPy. Inline-math macro declarations and use sites are
  currently a facts-only snapshot slice: QueryHost, engines, diagnostics, and public APIs do not
  expose or consume them, and full TeX expansion remains deferred.
- PolicyHost owns output-profile support, code-cell language-catalog policy, and
  diagnostic severity selection.
- Checkers own algebra, references, dimensions, symbols, and graph behavior.
- Cross-reference metadata is preserved in `FactSnapshot`, compared by the reference
  query view, and diagnosed by the reference engine. Built-in notebook metadata supplies
  recorded-output boundaries without executing code; arbitrary producer facts are not a
  public input surface.
- Generated-output checks consume explicit source-to-generated provenance facts;
  only `SourceOrigin.source_document_id` establishes the source mapping. The generated
  profile may supply source-kind and conversion-stage annotations when an origin omits
  them, but it never infers a source document or producer relationship.
- WorkspaceHost owns project-relative identity and applies the caller-supplied configured
  membership/visibility projection. It rejects raw document paths that collide after
  normalization. Orchestration injects the host into stateful scanners and frontends;
  compatibility, query, and graph paths use its pure lexical normalizer.
- Graph export models are built from scanner label/reference outputs and do not rescan documents.
- Reporters render diagnostics. They do not read files or run checks.
- CLI owns command-line plumbing only.

Import boundaries are enforced by import-linter no later than v0.1.0.

The reviewed R1 package boundary artifact is the
[module ownership map](architecture/module-ownership.md).
