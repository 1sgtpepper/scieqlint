from __future__ import annotations

import json
from dataclasses import replace
from pathlib import PurePosixPath

from scieqlint.app import _profile_snapshot, check_documents
from scieqlint.config.load import load_config
from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    ProfileConfig,
)
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.engine.structure import StructureEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.frontend.myst_blocks import (
    _directive_group_span,
    _fence_info_span,
    _option_value_span,
)
from scieqlint.frontend.myst_shared import DIRECTIVE_INFO_RE, QUARTO_OPTION_RE
from scieqlint.frontend.notebook import NotebookFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.policy import PolicyHost
from scieqlint.query.host import QueryHost


def markdown(text: str, path: str = "cells.md") -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath(path),
        text,
        DocumentKind.MARKDOWN,
    )


def notebook(data: object, path: str = "cells.ipynb") -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath(path),
        json.dumps(data, sort_keys=True),
        DocumentKind.NOTEBOOK,
    )


def profile_config() -> Config:
    return Config(
        profile=ProfileConfig(name="code-cell-metadata"),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )


def notebook_payload(*cells: object, language: str | None = "python") -> dict[str, object]:
    metadata: dict[str, object] = {}
    if language is not None:
        metadata["kernelspec"] = {"language": language, "name": f"{language}3"}
    return {
        "cells": list(cells),
        "metadata": metadata,
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def code_cell(*, metadata: object = None, source: object = "pass\n") -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {} if metadata is None else metadata,
        "outputs": [],
        "source": source,
    }


def source_slice(document: SourceDocument, span) -> str:
    assert span is not None
    return document.text[span.start : span.end]


def test_markdown_code_cell_label_resolves_reference_with_exact_spans() -> None:
    document = markdown(
        """```{code-cell} custom.kernel
:label: cell-demo
raise RuntimeError('must not execute')
```

See {ref}`cell-demo`.
"""
    )
    snapshot = MySTFrontend().lower((document,))
    [cell] = snapshot.code_cells

    assert cell.label == "cell-demo"
    assert cell.normalized_label == "cell-demo"
    assert cell.language == "custom.kernel"
    assert source_slice(document, cell.label_span) == "cell-demo"
    assert source_slice(document, cell.language_span) == "custom.kernel"
    assert QueryHost(snapshot).references.code_cell_targets() == (cell,)
    assert ReferenceEngine().run(QueryHost(snapshot)) == ()


def test_code_cell_name_option_is_a_reference_target() -> None:
    document = markdown(
        """```{code-cell} python
:name: named-cell
print(1)
```

See {ref}`Named cell <named-cell>`.
"""
    )
    snapshot = MySTFrontend().lower((document,))
    [cell] = snapshot.code_cells

    assert cell.label == "named-cell"
    assert source_slice(document, cell.label_span) == "named-cell"
    assert ReferenceEngine().run(QueryHost(snapshot)) == ()


def test_duplicate_code_cell_labels_report_only_later_cell_and_ambiguous_ref() -> None:
    document = markdown(
        """```{code-cell} python
:label: repeated-cell
print(1)
```

```{code-cell} julia
:label: repeated-cell
1
```

See {ref}`repeated-cell`.
"""
    )
    snapshot = MySTFrontend().lower((document,))
    query = QueryHost(snapshot)
    diagnostics = ReferenceEngine().run(query)

    assert query.references.duplicate_code_cell_targets() == {
        "repeated-cell": (snapshot.code_cells[1],)
    }
    assert [diagnostic.code for diagnostic in diagnostics] == ["REF010", "REF005"]
    duplicate = diagnostics[0]
    assert source_slice(document, duplicate.span) == "repeated-cell"
    assert duplicate.provenance_ids == tuple(sorted(cell.fact_id for cell in snapshot.code_cells))
    assert duplicate.properties == (("target", "repeated-cell"), ("target_count", "2"))


def test_code_cell_collision_with_anchor_reports_cell_label() -> None:
    document = markdown(
        """(shared-target)=
# Heading

```{code-cell} python
:label: shared-target
print(1)
```

See {ref}`shared-target`.
"""
    )
    snapshot = MySTFrontend().lower((document,))
    diagnostics = ReferenceEngine().run(QueryHost(snapshot))

    assert [diagnostic.code for diagnostic in diagnostics] == ["REF010", "REF005"]
    assert source_slice(document, diagnostics[0].span) == "shared-target"
    assert diagnostics[0].properties == (("target", "shared-target"), ("target_count", "2"))


def test_unlabeled_cell_does_not_hide_missing_reference() -> None:
    document = markdown(
        """```{code-cell} python
print(1)
```

See {ref}`missing-cell`.
"""
    )
    diagnostics = ReferenceEngine().run(QueryHost(MySTFrontend().lower((document,))))

    assert [diagnostic.code for diagnostic in diagnostics] == ["REF004"]
    assert diagnostics[0].message.endswith("missing-cell")


def test_language_profile_distinguishes_missing_malformed_and_custom_identifiers() -> None:
    document = markdown(
        """```{code-cell}
pass
```

```{code-cell} python shell
pass
```

```{code-cell} c++
pass
```

```{code-cell} brainfuck
pass
```

```{code-cell} custom.kernel-3
pass
```
"""
    )
    snapshot = MySTFrontend().lower((document,))
    query = QueryHost(snapshot)

    default = StructureEngine().run(query)
    profiled = StructureEngine(profile="code-cell-metadata").run(query)

    assert [diagnostic.code for diagnostic in default] == ["DIR010"]
    assert default[0].profile is None
    assert default[0].provenance_ids == ()
    assert default[0].properties == ()
    assert [diagnostic.code for diagnostic in profiled] == ["DIR010", "DIR013", "DIR013"]
    assert profiled[0].profile == "code-cell-metadata"
    assert profiled[0].properties == (("source_format", "markdown"), ("reason", "missing"))
    assert source_slice(document, profiled[1].span) == "python shell"
    assert profiled[1].properties == (
        ("source_format", "markdown"),
        ("language", "python shell"),
        ("reason", "invalid"),
    )
    assert source_slice(document, profiled[2].span) == "brainfuck"
    assert profiled[2].properties == (
        ("source_format", "markdown"),
        ("language", "brainfuck"),
        ("reason", "unknown"),
    )


def test_code_cell_language_policy_has_bounded_and_custom_escape_hatches() -> None:
    policy = PolicyHost(profile="code-cell-metadata")

    assert policy.code_cell_metadata_profile() == "code-cell-metadata"
    assert policy.code_cell_language_is_known("python")
    assert policy.code_cell_language_is_known("c++")
    assert policy.code_cell_language_is_known("custom.kernel-3")
    assert not policy.code_cell_language_is_known("brainfuck")


def test_notebook_cell_label_resolves_markdown_reference_without_execution() -> None:
    nb = notebook(
        notebook_payload(
            code_cell(
                metadata={"quarto": {"label": "cell-notebook"}},
                source="raise RuntimeError('must not execute')\n",
            )
        )
    )
    md = markdown("See {ref}`cell-notebook`.\n", "chapter.md")
    snapshot = _profile_snapshot((md, nb), profile_config())
    [cell] = [fact for fact in snapshot.code_cells if fact.source_format == "notebook"]

    assert cell.label == "cell-notebook"
    assert cell.normalized_label == "cell-notebook"
    assert cell.language == "python"
    assert cell.label_span is not None
    assert cell.label_span.cell == 0
    assert cell.language_span is not None
    assert cell.language_span.cell == 0
    assert ReferenceEngine(profile="code-cell-metadata").run(QueryHost(snapshot)) == ()


def test_notebook_source_language_overrides_kernel_and_preserves_cell_locations() -> None:
    document = notebook(
        notebook_payload(
            code_cell(source="pass\n"),
            code_cell(source="#| language: python shell\npass\n"),
            language=None,
        )
    )
    snapshot = NotebookFrontend().lower((document,))
    diagnostics = StructureEngine(profile="code-cell-metadata").run(QueryHost(snapshot))

    assert [cell.language for cell in snapshot.code_cells] == [None, "python shell"]
    assert [diagnostic.code for diagnostic in diagnostics] == ["DIR010", "DIR013"]
    assert [diagnostic.span.cell for diagnostic in diagnostics if diagnostic.span] == [0, 1]
    assert all(diagnostic.span and diagnostic.span.cell_line == 1 for diagnostic in diagnostics)
    assert [dict(diagnostic.properties)["source_format"] for diagnostic in diagnostics] == [
        "notebook",
        "notebook",
    ]


def test_check_documents_profile_is_input_order_deterministic() -> None:
    first = markdown(
        """```{code-cell} python
:label: repeated
pass
```
""",
        "a.md",
    )
    second = markdown(
        """```{code-cell} python
:label: repeated
pass
```
See {ref}`repeated`.
""",
        "b.md",
    )

    forward = check_documents((first, second), config=profile_config())
    reverse = check_documents((second, first), config=profile_config())

    def contract(result):
        return tuple(
            (
                diagnostic.code,
                diagnostic.span.path.as_posix() if diagnostic.span else None,
                diagnostic.span.line if diagnostic.span else None,
                diagnostic.span.col if diagnostic.span else None,
                diagnostic.message,
                diagnostic.provenance_ids,
                diagnostic.properties,
            )
            for diagnostic in result.diagnostics
            if diagnostic.code in {"REF005", "REF010", "DIR010", "DIR013"}
        )

    assert contract(forward) == contract(reverse)
    assert [item[0] for item in contract(forward)] == ["REF010", "REF005"]


def test_code_cell_metadata_profile_loads_from_strict_config(tmp_path) -> None:
    path = tmp_path / "scieqlint.toml"
    path.write_text('[profile]\nname = "code-cell-metadata"\n', encoding="utf-8")

    loaded = load_config(path)

    assert loaded.profile.name == "code-cell-metadata"


def test_code_cell_span_helpers_bound_empty_and_inconsistent_fence_metadata() -> None:
    document = markdown(
        """```python
#| label:
pass
```

```{code-cell} python
pass
```
"""
    )
    snapshot = MySTFrontend().lower((document,))
    plain_fence, directive_fence = snapshot.fences
    directive_match = DIRECTIVE_INFO_RE.match(directive_fence.info_string)
    assert directive_match is not None

    assert snapshot.code_cells[0].label_span is None
    assert (
        _option_value_span(
            document,
            replace(plain_fence, body_span=None),
            QUARTO_OPTION_RE,
            "label",
        )
        is None
    )
    assert _fence_info_span(document, plain_fence, None) is None
    assert (
        _fence_info_span(document, replace(plain_fence, info_string="missing"), "python")
        == plain_fence.opener_span
    )
    assert (
        _directive_group_span(
            document,
            replace(directive_fence, info_string="missing"),
            directive_match,
            "arg",
        )
        == directive_fence.opener_span
    )
