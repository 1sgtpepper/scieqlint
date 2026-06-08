# Review guide

Review order:

1. Scope.
2. Correctness.
3. Tests and docs.
4. Style.

Blocking comments should identify violated contracts or missing release checks. Non-blocking comments should be labeled as suggestions.

Do not widen a contributor's PR. Open follow-up issues instead.

Use the PR dependency checklist before style review. A behavior change is not
ready when dependent diagnostics, limitations, schemas, golden files,
integration docs, release notes, or changelog entries are missing.

Do not mark a PR ready for review until required CI checks pass.
