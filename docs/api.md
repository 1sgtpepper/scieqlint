# Public API

The stable API surface is exported from `scieqlint.api`:

- `check_paths(paths, *, config_path=None, no_algebra=False, inline_math=False,
  strict_unknowns=False, absolute_paths=False)`
- `check_documents(documents, *, config, accessibility_metadata=None)`
- `graph_paths(paths, *, config_path=None)`
- `graph_documents(documents, *, config)`
- `load_config(path=None, *, preset=None)`

Public API usage:

```python
from pathlib import Path
from scieqlint.api import (
    check_documents,
    check_paths,
    graph_documents,
    graph_paths,
    load_config,
)

config = load_config(Path("scieqlint.toml"))
result = check_paths([Path("README.md")], config_path=Path("scieqlint.toml"))
graph = graph_paths([Path("README.md")], config_path=Path("scieqlint.toml"))
print(result.exit_code())
```

API calls must not print to stdout/stderr and must not call `sys.exit`.
`check_paths` and `graph_paths` are the path-based APIs and apply the same project
discovery, config lookup, file ordering, ignore rules, source loading, and display
path rules. Checks continue after a source read or decode failure and return
`INP001`; graph construction is all-or-nothing and raises a controlled `ValueError`
with `INP001` context chained from the original error. Baselines remain check-only.
Explicit existing files must use a supported `.md`, `.markdown`, `.tex`, or `.ipynb`
suffix; the path APIs raise `ValueError` for unsupported paths and the CLI reports the
same failure with exit status 2. `DocumentKind.UNKNOWN` is rejected by the document
APIs. Directory and glob discovery continue to ignore unsupported files.
`check_paths` and `graph_paths` raise `FileNotFoundError` when an explicitly
provided non-glob path does not exist. Existing paths are treated literally even
when their names contain glob characters; only nonexistent strings with glob
syntax are expanded.
`check_documents` and `graph_documents` are the already-loaded-document APIs and
do not read baseline files from disk. Path-based APIs preserve their analysis result
when output-safety metadata is unavailable; that metadata is required only by the
CLI guard before writing a file output.

`accessibility_metadata` is a caller-owned mapping from a source-owned inline-math
accessibility ID to accessible text. An ID has the form
`<document-path>::inline-math::<delimiter-kind>::<trimmed-body>`; repeated identical
source tokens append a deterministic occurrence suffix such as `::1`. These identities
do not depend on the token's byte offset, so edits before a formula that do not add an
earlier identical token do not invalidate the mapping. SciEqLint applies it at the
orchestration boundary; it does not infer alternative text from surrounding prose. An
unknown accessibility ID is rejected. The
`[project].visibility` configuration table uses each document's project-relative path as
its key and accepts `"visible"`, `"hidden"`, or `"excluded"`. Omitted documents are
visible, and a configured path that is not present in the analyzed project is rejected.
Hidden and excluded equation or code-cell targets remain queryable as non-visible facts,
do not resolve ordinary references, and excluded documents are omitted from
`graph_documents()`.

Generated-output validation never infers a source document from a filename, input order,
or directory layout. A caller that wants the `generated-myst` profile to compare a
generated document with its source attaches an explicit `SourceOrigin` to that
`SourceDocument`:

```python
from pathlib import PurePosixPath
from scieqlint.api import check_documents
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin

source = SourceDocument.from_text(
    PurePosixPath("source/lecture.md"),
    "(energy)=\n## Energy\n",
    DocumentKind.MARKDOWN,
)
generated = SourceDocument.from_text(
    PurePosixPath("translated/lecture.md"),
    "## Energy\n",
    DocumentKind.MARKDOWN,
    origin=SourceOrigin(
        source_document_id="source/lecture.md",
        source_kind="markdown",
        conversion_stage="translation",
        preserved_anchor_inventory=("energy",),
    ),
)
result = check_documents(
    (source, generated),
    config=Config(profile=ProfileConfig(name="generated-myst")),
)
```

An absent explicit source mapping means that source-to-generated identity is unknown,
so the loaded-document API does not manufacture a provenance relationship. The
path-based API records the generated document and any configured profile metadata
when `generated-myst` is selected, but it still leaves source-document identity and
preserved-anchor comparison to an explicit `SourceOrigin`.

Path-based diagnostics and graph spans retain the caller-visible lexical input
spelling. Relative inputs keep that spelling; absolute inputs are rendered
relative to the current working directory by default. For `check_paths()`,
`absolute_paths=True` retains an explicitly absolute input's lexical spelling
without resolving symlinks; `graph_paths()` always uses the default presentation.
When an absolute input and the current directory have different native roots,
default presentation raises `ValueError` rather than leak an absolute path or
collapse distinct roots. Checks may opt into absolute paths; graph inputs must be
expressed on the current root.

`CheckResult` exposes `diagnostics`, `files_checked`, `math_blocks_checked`,
`config_path`, `version`, `show_suppressed`, and `exit_code()`. `exit_code()`
returns `1` only when an unsuppressed error diagnostic exists.

`Diagnostic` exposes stable diagnostic data used by reporters and JSON output:
`code`, `severity`, `message`, `span`, `equation`, `detail`, `hint`, `rule`,
`suppressed`, and `suppression_reason`.
Semantic generated provenance remains available on the in-process diagnostic;
reporters and JSON output use the versioned `SchemaHost` projection for public
property names and provenance IDs.

`load_config(path, preset="generated-myst")` or
`load_config(path, preset="mechanics")` loads packaged preset defaults before
the user config file, so user config values override preset values. The
`generated-myst` preset supplies scanner and parser defaults and selects the
generated-output profile. User config values still override the preset.
