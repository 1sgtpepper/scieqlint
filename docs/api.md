# Public API

The stable API surface is exported from `scieqlint.api`:

- `check_paths(paths, *, config_path=None, no_algebra=False, inline_math=False,
  strict_unknowns=False, absolute_paths=False)`
- `check_documents(documents, *, config)`
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

Programmatic provenance identifiers, source kinds, and conversion stages are
trimmed when constructed; blank values raise `ValueError` before analysis.

An absent origin means that source-to-generated identity is unknown, so the generated
profile does not manufacture a provenance relationship. The `generated-myst` and
`cross-format-references` profiles require each supplied `SourceDocument.path` to be
unique; duplicate paths raise `ValueError` before analysis. Other profiles retain the
ordinary document-lowering behavior.

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
`suppressed`, `suppression_reason`, `profile`, `provenance_ids`, and `properties`.
`profile` is optional and identifies the validation profile that produced the
diagnostic. `provenance_ids` contains caller-supplied provenance fact IDs and is
empty when no provenance is available; `properties` contains string-valued rule
metadata and is empty when no properties are present. For generated origins, one
origin uses unprefixed property names, while multiple origins use
`provenance_1_*`, `provenance_2_*`, and later names; missing origin fields are omitted.
Property names are unique after projection: later rule values replace earlier values,
and SchemaHost-owned profile and provenance values take precedence over colliding rule
properties.
These optional fields are omitted from JSON output when unset or empty.
JSON output without projection metadata retains schema version `0.1`. If any
emitted diagnostic contains `profile`, `provenance_ids`, or `properties`, the
result identifies itself as `0.2` and validates against the packaged 0.2 result
and diagnostic schemas. The 0.1 schemas remain unchanged.

`load_config(path, preset="generated-myst")` or
`load_config(path, preset="mechanics")` loads packaged preset defaults before
the user config file, so user config values override preset values. The
`generated-myst` preset supplies the path-based generated-document validation policy,
including source-only generated-output diagnostics. Provenance-backed checks still
require already-loaded `SourceDocument` values with explicit `SourceOrigin` metadata;
the path-based CLI does not manufacture that relationship.
