from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

from scieqlint.api import check_documents as public_check_documents
from scieqlint.app import _profile_snapshot, check_documents
from scieqlint.config.load import load_config
from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    ProfileConfig,
    ProjectConfig,
    ProjectVisibility,
)
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.engine.structure import StructureEngine
from scieqlint.facts.structure import CodeCellFact
from scieqlint.frontend import notebook_input
from scieqlint.frontend.myst import MySTFrontend
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


@pytest.mark.parametrize("kind", ["markdown", "notebook"])
@pytest.mark.parametrize("value", ["fig-theme", "'fig-theme'", '"fig-theme"'])
def test_source_labels_keep_scalar_identity_and_original_value_span(kind: str, value: str) -> None:
    source = f"#| label: {value}\nplot()\n"
    reference = "See {ref}`fig-theme`.\n"
    document = (
        markdown(f"```python\n{source}```\n\n{reference}")
        if kind == "markdown"
        else notebook(
            notebook_payload(
                code_cell(source=source),
                {"cell_type": "markdown", "metadata": {}, "source": reference},
            )
        )
    )
    frontend = MySTFrontend() if kind == "markdown" else NotebookFrontend()

    [cell] = frontend.lower((document,)).code_cells

    assert cell.label == cell.normalized_label == "fig-theme"
    text = (
        source_slice(document, cell.label_span)
        if kind == "markdown"
        else decoded_source_segment_text(document, cell.label_span)
    )
    assert text == value
    result = public_check_documents((document,), config=profile_config())
    assert result.diagnostics == ()


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


def source_segment_text(document: SourceDocument, span) -> str:
    assert span is not None
    assert span.segments
    return "".join(
        document.text[start:end] for segment in span.segments for start, end in segment.ranges
    )


def decoded_source_segment_text(document: SourceDocument, span) -> str:
    assert span is not None
    assert span.segments
    decoded: list[str] = []
    for segment in span.segments:
        for start, end in segment.ranges:
            value = json.loads(f'"{document.text[start:end]}"')
            assert isinstance(value, str)
            decoded.append(value)
    return "".join(decoded)


def code_cell_fact_for_label(*, label: str | None, normalized_label: str | None) -> CodeCellFact:
    return CodeCellFact(
        fact_id="cell",
        document_id="cells.md",
        span=None,
        fence_fact_id="fence",
        directive_fact_id=None,
        language="python",
        engine="python",
        options=(),
        label=label,
        normalized_label=normalized_label,
    )


@pytest.mark.parametrize(
    ("label", "normalized_label", "message"),
    [
        (
            "#cell",
            "other",
            "code-cell normalized label must be a non-empty canonical normalization of label",
        ),
        (
            "cell",
            "",
            "code-cell normalized label must be a non-empty canonical normalization of label",
        ),
        (
            "#",
            "",
            "code-cell normalized label must be a non-empty canonical normalization of label",
        ),
    ],
)
def test_code_cell_fact_rejects_invalid_label_identity(
    label: str | None,
    normalized_label: str | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message) as exc_info:
        code_cell_fact_for_label(label=label, normalized_label=normalized_label)

    assert str(exc_info.value) == message


@pytest.mark.parametrize(
    ("label", "normalized_label"),
    [("cell", "cell"), (" #cell ", "cell"), ("##cell", "#cell"), (None, None)],
)
def test_code_cell_fact_accepts_canonical_label_identity(
    label: str | None,
    normalized_label: str | None,
) -> None:
    fact = code_cell_fact_for_label(label=label, normalized_label=normalized_label)

    assert (fact.label, fact.normalized_label) == (label, normalized_label)


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


def test_myst_code_cell_label_span_accounts_for_blank_option_prefix_lines() -> None:
    document = markdown(
        """```{code-cell} python

:label: blank-separated
raise RuntimeError('must not execute')
```
"""
    )

    [cell] = MySTFrontend().lower((document,)).code_cells

    assert cell.label == "blank-separated"
    assert cell.label_span is not None
    assert source_slice(document, cell.label_span) == "blank-separated"
    assert cell.label_span.start == document.text.index("blank-separated")


def test_public_markdown_link_resolves_code_cell_without_legacy_reference_error() -> None:
    document = markdown(
        """```{code-cell} python
:label: result
pass
```

See [result](#result) and [missing](#missing).
"""
    )

    result = public_check_documents((document,), config=profile_config())

    reference_diagnostics = [
        diagnostic for diagnostic in result.diagnostics if diagnostic.code.startswith("REF")
    ]
    assert [diagnostic.code for diagnostic in reference_diagnostics] == ["REF002"]
    assert source_slice(document, reference_diagnostics[0].span) == "missing"
    assert reference_diagnostics[0].profile is None


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
        (PurePosixPath("cells.md"), "repeated-cell"): (snapshot.code_cells[1],)
    }
    assert [diagnostic.code for diagnostic in diagnostics] == ["REF010", "REF005"]
    duplicate = diagnostics[0]
    assert source_slice(document, duplicate.span) == "repeated-cell"
    assert duplicate.provenance_ids == tuple(sorted(cell.fact_id for cell in snapshot.code_cells))
    assert duplicate.properties == (("target", "cells.md#repeated-cell"), ("target_count", "2"))


def test_duplicate_code_cell_diagnostics_keep_bounded_exact_evidence() -> None:
    cell_count = 32
    document = markdown(
        "\n".join(
            "```{code-cell} python\n:label: repeated-cell\npass\n```" for _ in range(cell_count)
        )
    )
    snapshot = MySTFrontend().lower((document,))

    diagnostics = tuple(
        diagnostic
        for diagnostic in ReferenceEngine().run(QueryHost(snapshot))
        if diagnostic.code == "REF010"
    )

    assert len(diagnostics) == cell_count - 1
    canonical = snapshot.code_cells[0]
    for diagnostic, duplicate in zip(diagnostics, snapshot.code_cells[1:], strict=True):
        assert source_slice(document, diagnostic.span) == "repeated-cell"
        assert diagnostic.provenance_ids == tuple(sorted((canonical.fact_id, duplicate.fact_id)))
        assert diagnostic.properties == (
            ("target", "cells.md#repeated-cell"),
            ("target_count", str(cell_count)),
        )


def test_equal_code_cell_labels_in_distinct_members_do_not_collide() -> None:
    first = markdown(
        """```{code-cell} python
:label: shared-cell
print(1)
```
""",
        "first.md",
    )
    second = markdown(
        """```{code-cell} python
:label: shared-cell
print(2)
```
""",
        "second.md",
    )
    snapshot = MySTFrontend().lower((first, second))
    query = QueryHost(snapshot)

    assert query.references.duplicate_code_cell_targets() == {}
    assert not [item for item in ReferenceEngine().run(query) if item.code == "REF010"]


def test_public_notebook_code_cell_collisions_use_member_and_cell_identity() -> None:
    notebook_document = notebook(
        notebook_payload(
            code_cell(metadata={"label": "shared-cell"}),
            code_cell(metadata={"label": "shared-cell"}),
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "See {ref}`shared-cell`.\n",
            },
        )
    )
    first_member = notebook(
        notebook_payload(code_cell(metadata={"label": "shared-cell"})),
        "first.ipynb",
    )
    second_member = notebook(
        notebook_payload(code_cell(metadata={"label": "shared-cell"})),
        "second.ipynb",
    )

    duplicate_result = public_check_documents((notebook_document,), config=profile_config())
    distinct_result = public_check_documents(
        (first_member, second_member),
        config=profile_config(),
    )

    assert [item.code for item in duplicate_result.diagnostics if item.code == "REF010"] == [
        "REF010"
    ]
    assert [item.code for item in duplicate_result.diagnostics if item.code == "REF005"] == [
        "REF005"
    ]
    assert not [item for item in distinct_result.diagnostics if item.code == "REF010"]


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
    assert diagnostics[0].provenance_ids == tuple(
        sorted((snapshot.target_anchors[0].fact_id, snapshot.code_cells[0].fact_id))
    )
    assert diagnostics[0].properties == (
        ("target", "cells.md#shared-target"),
        ("target_count", "2"),
    )


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


def test_language_profile_uses_project_catalog_after_syntax_validation() -> None:
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
    profiled = StructureEngine(policy=PolicyHost(profile="code-cell-metadata")).run(query)
    configured = StructureEngine(
        policy=PolicyHost(
            profile="code-cell-metadata",
            code_cell_languages=("python", "c++", "custom.kernel-3"),
        ),
    ).run(query)

    assert [diagnostic.code for diagnostic in default] == ["DIR010"]
    assert default[0].profile is None
    assert default[0].provenance_ids == ()
    assert default[0].properties == ()
    assert [diagnostic.code for diagnostic in profiled] == ["DIR010", "DIR013"]
    assert profiled[0].profile == "code-cell-metadata"
    assert profiled[0].properties == (("source_format", "markdown"), ("reason", "missing"))
    assert source_slice(document, profiled[1].span) == "python shell"
    assert profiled[1].properties == (
        ("source_format", "markdown"),
        ("language", "python shell"),
        ("reason", "invalid"),
    )
    assert [diagnostic.code for diagnostic in configured] == ["DIR010", "DIR013", "DIR013"]
    assert source_slice(document, configured[2].span) == "brainfuck"
    assert configured[2].properties == (
        ("source_format", "markdown"),
        ("language", "brainfuck"),
        ("reason", "unknown"),
    )


LANGUAGE_NOTEBOOK = r"""{
  "cells": [
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {"language": "python"},
      "outputs": [],
      "source": "pass\n"
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": "pass\n"
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {"language": "python shell"},
      "outputs": [],
      "source": "pass\n"
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {"language": "brainfuck"},
      "outputs": [],
      "source": "pass\n"
    }
  ],
  "metadata": {},
  "nbformat": 4,
  "nbformat_minor": 5
}"""


MALFORMED_LANGUAGE_NOTEBOOK = r"""{
  "cells": [
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {"language": "custom.kernel"},
      "outputs": [],
      "source": "pass\n"
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": "pass\n"
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {"language": {"name": "python"}},
      "outputs": [],
      "source": "pass\n"
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {"language": null},
      "outputs": [],
      "source": "pass\n"
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {"language": ""},
      "outputs": [],
      "source": "pass\n"
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": "#| language:\npass\n"
    }
  ],
  "metadata": {"kernelspec": {"language": "python", "name": "python3"}},
  "nbformat": 4,
  "nbformat_minor": 5
}"""


def test_notebook_language_metadata_preserves_malformed_values_and_decoder_spans() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("malformed-language.ipynb"),
        MALFORMED_LANGUAGE_NOTEBOOK,
        DocumentKind.NOTEBOOK,
    )
    snapshot = NotebookFrontend().lower((document,))
    diagnostics = StructureEngine(
        policy=PolicyHost(
            profile="code-cell-metadata",
            code_cell_languages=("python", "custom.kernel"),
        ),
    ).run(QueryHost(snapshot))

    [valid, defaulted, mapping, null_value, empty_metadata, empty_source] = snapshot.code_cells
    assert [cell.language for cell in snapshot.code_cells] == [
        "custom.kernel",
        "python",
        '<json:{"name":"python"}>',
        "<json:null>",
        '<json:"">',
        '<json:"">',
    ]
    assert valid.language_span is not None
    assert source_slice(document, valid.language_span) == "custom.kernel"
    assert defaulted.language_span is not None
    assert source_slice(document, defaulted.language_span) == "python"
    assert mapping.language_span is not None
    assert source_slice(document, mapping.language_span) == '{"name": "python"}'
    assert null_value.language_span is not None
    assert source_slice(document, null_value.language_span) == "null"
    assert mapping.language_span.start == document.text.index('{"name": "python"}')
    assert mapping.language_span.end == mapping.language_span.start + len('{"name": "python"}')
    assert null_value.language_span.start == document.text.index('"language": null') + len(
        '"language": '
    )
    assert null_value.language_span.end == null_value.language_span.start + len("null")
    assert empty_metadata.language_span is not None
    assert source_slice(document, empty_metadata.language_span) == '""'
    assert empty_metadata.language_span.start == document.text.index('"language": ""') + len(
        '"language": '
    )
    assert empty_metadata.language_span.end == empty_metadata.language_span.start + len('""')
    assert empty_source.language_span is not None
    assert source_slice(document, empty_source.language_span) == ""
    assert empty_source.language_span.start == document.text.index("#| language:") + len(
        "#| language:"
    )
    root_language = document.text.rindex('"language": "python"')
    assert defaulted.language_span.start == document.text.index('"python"', root_language) + 1
    assert [
        (diagnostic.code, dict(diagnostic.properties)["reason"]) for diagnostic in diagnostics
    ] == [
        ("DIR013", "invalid"),
        ("DIR013", "invalid"),
        ("DIR013", "invalid"),
        ("DIR013", "invalid"),
    ]
    assert diagnostics[0].span == mapping.language_span
    assert diagnostics[1].span == null_value.language_span
    assert diagnostics[2].span == empty_metadata.language_span
    assert diagnostics[3].span == empty_source.language_span


def test_empty_source_label_clears_metadata_without_invalid_root_defaults() -> None:
    payload = notebook_payload(
        code_cell(metadata={"label": "metadata-label"}, source="#| label:\npass\n")
    )
    payload["metadata"] = None

    [cell] = NotebookFrontend().lower((notebook(payload),)).code_cells

    assert cell.options == (("label", ""),)
    assert cell.label is None
    assert cell.normalized_label is None
    assert cell.label_span is None
    assert cell.language is None
    assert cell.language_span is None


def test_notebook_language_policy_matches_markdown_with_exact_spans() -> None:
    notebook_document = SourceDocument.from_text(
        PurePosixPath("language.ipynb"),
        LANGUAGE_NOTEBOOK,
        DocumentKind.NOTEBOOK,
    )
    markdown_document = markdown(
        """```{code-cell} python
pass
```

```{code-cell}
pass
```

```{code-cell} python shell
pass
```

```{code-cell} brainfuck
pass
```
""",
        "language.md",
    )
    policy = PolicyHost(
        profile="code-cell-metadata",
        code_cell_languages=("python",),
    )
    notebook_snapshot = NotebookFrontend().lower((notebook_document,))
    markdown_snapshot = MySTFrontend().lower((markdown_document,))
    notebook_diagnostics = StructureEngine(
        policy=policy,
    ).run(QueryHost(notebook_snapshot))
    markdown_diagnostics = StructureEngine(
        policy=policy,
    ).run(QueryHost(markdown_snapshot))

    def language_contract(diagnostics):
        return tuple(
            (
                diagnostic.code,
                dict(diagnostic.properties).get("language"),
                dict(diagnostic.properties).get("reason"),
            )
            for diagnostic in diagnostics
        )

    assert language_contract(notebook_diagnostics) == language_contract(markdown_diagnostics)
    assert language_contract(notebook_diagnostics) == (
        ("DIR010", None, "missing"),
        ("DIR013", "python shell", "invalid"),
        ("DIR013", "brainfuck", "unknown"),
    )
    [valid, missing, invalid, unknown] = notebook_snapshot.code_cells
    assert valid.language_span is not None
    assert source_slice(notebook_document, valid.language_span) == "python"
    assert (
        valid.language_span.start,
        valid.language_span.end,
        valid.language_span.line,
        valid.language_span.col,
        valid.language_span.end_line,
        valid.language_span.end_col,
    ) == (111, 117, 6, 33, 6, 38)
    assert missing.language_span is None
    assert missing.span is not None
    assert (
        missing.span.start,
        missing.span.end,
        missing.span.line,
        missing.span.col,
        missing.span.end_line,
        missing.span.end_col,
    ) == (178, 311, 10, 5, 16, 5)
    assert invalid.language_span is not None
    assert source_slice(notebook_document, invalid.language_span) == "python shell"
    assert (
        invalid.language_span.start,
        invalid.language_span.end,
        invalid.language_span.line,
        invalid.language_span.col,
        invalid.language_span.end_line,
        invalid.language_span.end_col,
    ) == (409, 421, 20, 33, 20, 44)
    assert unknown.language_span is not None
    assert source_slice(notebook_document, unknown.language_span) == "brainfuck"
    assert (
        unknown.language_span.start,
        unknown.language_span.end,
        unknown.language_span.line,
        unknown.language_span.col,
        unknown.language_span.end_line,
        unknown.language_span.end_col,
    ) == (574, 583, 27, 33, 27, 41)
    assert notebook_diagnostics[0].span == missing.span
    assert notebook_diagnostics[1].span == invalid.language_span
    assert notebook_diagnostics[2].span == unknown.language_span
    assert (
        source_slice(notebook_document, notebook_diagnostics[0].span)
        == notebook_document.text[missing.span.start : missing.span.end]
    )
    assert source_slice(notebook_document, notebook_diagnostics[1].span) == "python shell"
    assert source_slice(notebook_document, notebook_diagnostics[2].span) == "brainfuck"
    assert source_slice(markdown_document, markdown_diagnostics[0].span) == (
        "```{code-cell}\npass\n```\n"
    )
    assert source_slice(markdown_document, markdown_diagnostics[1].span) == "python shell"
    assert source_slice(markdown_document, markdown_diagnostics[2].span) == "brainfuck"


def test_code_cell_language_policy_defaults_open_and_honors_project_catalog() -> None:
    policy = PolicyHost(profile="code-cell-metadata")
    configured = PolicyHost(
        profile="code-cell-metadata",
        code_cell_languages=("python", "c++"),
    )

    assert policy.code_cell_metadata_profile() == "code-cell-metadata"
    assert policy.code_cell_language_is_known("python")
    assert policy.code_cell_language_is_known("c++")
    assert policy.code_cell_language_is_known("custom.kernel-3")
    assert policy.code_cell_language_is_known("brainfuck")
    assert configured.code_cell_language_is_known("python")
    assert not configured.code_cell_language_is_known("brainfuck")


def test_check_documents_applies_project_language_catalog() -> None:
    document = markdown("```{code-cell} brainfuck\npass\n```\n")

    open_result = check_documents((document,), config=profile_config())
    closed_result = check_documents(
        (document,),
        config=Config(
            profile=ProfileConfig(name="code-cell-metadata"),
            checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
            project=ProjectConfig(code_cell_languages=("python",)),
        ),
    )

    assert not any(item.code == "DIR013" for item in open_result.diagnostics)
    assert [item.code for item in closed_result.diagnostics if item.code == "DIR013"] == ["DIR013"]


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
    assert source_slice(nb, cell.label_span) == "cell-notebook"
    assert cell.label_span.cell == 0
    assert cell.language_span is not None
    assert source_slice(nb, cell.language_span) == "python"
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
    diagnostics = StructureEngine(policy=PolicyHost(profile="code-cell-metadata")).run(
        QueryHost(snapshot)
    )

    assert [cell.language for cell in snapshot.code_cells] == [None, "python shell"]
    assert [diagnostic.code for diagnostic in diagnostics] == ["DIR010", "DIR013"]
    assert [diagnostic.span.cell for diagnostic in diagnostics if diagnostic.span] == [0, 1]
    assert all(diagnostic.span and diagnostic.span.cell_line == 1 for diagnostic in diagnostics)
    assert source_slice(document, snapshot.code_cells[1].language_span) == "python shell"
    assert [dict(diagnostic.properties)["source_format"] for diagnostic in diagnostics] == [
        "notebook",
        "notebook",
    ]


@pytest.mark.parametrize("visibility", ["hidden", "excluded"])
def test_nonvisible_notebook_code_cells_keep_facts_without_language_or_reference_diagnostics(
    visibility: ProjectVisibility,
) -> None:
    hidden_document = notebook(
        notebook_payload(
            code_cell(
                metadata={"label": "shared-cell", "fig-cap": "Figure"},
                source="#| language: brainfuck\npass\n",
            )
        ),
        "hidden.ipynb",
    )
    visible_document = notebook(
        notebook_payload(
            code_cell(metadata={"label": "shared-cell"}),
        ),
        "visible.ipynb",
    )
    config = Config(
        profile=ProfileConfig(name="code-cell-metadata"),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
        project=ProjectConfig(
            visibility=(("hidden.ipynb", visibility),),
            code_cell_languages=("python",),
        ),
    )

    snapshot = _profile_snapshot((hidden_document, visible_document), config)
    query = QueryHost(snapshot)
    hidden_cell, visible_cell = snapshot.code_cells

    assert query.references.code_cell_targets() == (hidden_cell, visible_cell)
    assert hidden_cell.visibility == visibility
    assert visible_cell.visibility == "visible"
    if visibility == "hidden":
        assert query.references.hidden_code_cell_targets() == (hidden_cell,)
    else:
        assert query.references.excluded_code_cell_targets() == (hidden_cell,)
    assert query.portability.quarto_crossref_label_issues() == ()
    assert query.references.duplicate_code_cell_targets() == {}
    assert query.structure.invalid_code_cell_languages() == ()
    assert (
        StructureEngine(
            policy=PolicyHost(
                profile="code-cell-metadata",
                code_cell_languages=("python",),
            ),
        ).run(query)
        == ()
    )
    assert ReferenceEngine(profile="code-cell-metadata").run(query) == ()


@pytest.mark.parametrize("visibility", ["hidden", "excluded"])
def test_public_nonvisible_notebook_code_cells_emit_no_language_diagnostics(
    visibility: ProjectVisibility,
) -> None:
    hidden_document = notebook(
        notebook_payload(
            code_cell(metadata={"language": "python shell"}),
            language=None,
        ),
        "hidden.ipynb",
    )
    visible_document = notebook(
        notebook_payload(
            code_cell(metadata={"language": "python"}),
            language=None,
        ),
        "visible.ipynb",
    )
    config = Config(
        profile=ProfileConfig(name="code-cell-metadata"),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
        project=ProjectConfig(
            visibility=(("hidden.ipynb", visibility),),
            code_cell_languages=("python",),
        ),
    )

    result = public_check_documents((hidden_document, visible_document), config=config)

    assert [
        diagnostic.code for diagnostic in result.diagnostics if diagnostic.code.startswith("DIR")
    ] == []


@pytest.mark.parametrize(
    "source",
    [
        """```{code-cell} python
:label: #
pass
```
""",
        "```{code-cell} python\n:label:   #   \npass\n```\n",
        """```{python}
#| label: #
pass
```
""",
        "```python\n#| label:   #   \npass\n```\n",
    ],
)
def test_malformed_markdown_code_cell_labels_are_unlabeled_and_public_safe(source: str) -> None:
    document = markdown(source)

    result = public_check_documents((document,), config=profile_config())
    [cell] = MySTFrontend().lower((document,)).code_cells

    assert not any(diagnostic.code == "INP001" for diagnostic in result.diagnostics)
    assert cell.label is None
    assert cell.normalized_label is None
    assert cell.label_span is None


@pytest.mark.parametrize("metadata", [{"label": "#"}, {"label": "  #  "}])
def test_malformed_notebook_metadata_labels_are_unlabeled_and_public_safe(
    metadata: dict[str, str],
) -> None:
    document = notebook(notebook_payload(code_cell(metadata=metadata)))

    result = public_check_documents((document,), config=profile_config())
    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert not any(diagnostic.code == "INP001" for diagnostic in result.diagnostics)
    assert cell.label is None
    assert cell.normalized_label is None
    assert cell.label_span is None


@pytest.mark.parametrize("source", ["#| label: #\npass\n", "#| label:   #  \npass\n"])
def test_malformed_notebook_source_labels_are_unlabeled_and_public_safe(source: str) -> None:
    document = notebook(notebook_payload(code_cell(source=source)))

    result = public_check_documents((document,), config=profile_config())
    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert not any(diagnostic.code == "INP001" for diagnostic in result.diagnostics)
    assert cell.label is None
    assert cell.normalized_label is None
    assert cell.label_span is None


def test_notebook_source_list_label_span_preserves_each_json_string_segment() -> None:
    document = notebook(
        notebook_payload(
            code_cell(source=["#| label: split-", "label\r\npass\r\n"]),
        )
    )

    result = public_check_documents((document,), config=profile_config())
    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert not any(diagnostic.code == "INP001" for diagnostic in result.diagnostics)
    assert cell.label == "split-label"
    assert cell.normalized_label == "split-label"
    assert source_segment_text(document, cell.label_span) == "split-label"
    second_item_start = document.text.index('"label\\r\\n')
    assert cell.label_span.start < second_item_start
    assert cell.label_span.end > second_item_start


def test_notebook_source_list_label_span_decodes_escapes_and_split_crlf() -> None:
    document = notebook(
        notebook_payload(
            code_cell(source=["# comment\r", "\n#| label: caf", "é-😀\r", "\npass\r\n"]),
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "See {ref}`café-😀`.\n",
            },
        )
    )

    result = public_check_documents((document,), config=profile_config())
    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert result.diagnostics == ()
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert result.exit_code() == 0
    assert cell.label == "café-😀"
    assert cell.label_span is not None
    assert cell.label_span.cell_line == 2
    assert decoded_source_segment_text(document, cell.label_span) == "café-😀"
    assert len(cell.label_span.segments) == len("café-😀")


def test_notebook_source_label_after_large_preamble_keeps_exact_span() -> None:
    preamble = "# comment before options\n" * 400
    assert len(preamble) > 8192
    document = notebook(
        notebook_payload(
            code_cell(source=f"{preamble}#| label: after-preamble\npass\n"),
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "See {ref}`after-preamble`.\n",
            },
        )
    )

    result = public_check_documents((document,), config=profile_config())
    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert result.diagnostics == ()
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert result.exit_code() == 0
    assert cell.label == "after-preamble"
    assert cell.normalized_label == "after-preamble"
    assert cell.label_span is not None
    assert cell.label_span.cell_line == 401
    assert decoded_source_segment_text(document, cell.label_span) == "after-preamble"


@pytest.mark.parametrize(
    "separator", ["\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"]
)
def test_notebook_source_label_uses_python_splitline_boundaries(separator: str) -> None:
    document = notebook(
        notebook_payload(code_cell(source=f"# comment{separator}#| label: exotic{separator}pass"))
    )

    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert cell.label == "exotic"
    assert cell.label_span is not None
    assert cell.label_span.cell_line == 2
    assert decoded_source_segment_text(document, cell.label_span) == "exotic"


def test_large_notebook_code_source_does_not_materialize_character_ranges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_source_ranges(*args, **kwargs):
        raise AssertionError("code-cell source mapping must stay sparse")

    monkeypatch.setattr(notebook_input, "_source_ranges", unexpected_source_ranges)
    source = "pass\n" * 30_000
    document = notebook(notebook_payload(code_cell(source=source)))

    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert cell.raw == source
    assert cell.label is None
    assert cell.label_span is None


def test_source_label_after_executable_code_is_not_an_option() -> None:
    source = f"value = {'1' * 30_000}\n#| label: ignored\n"
    document = notebook(notebook_payload(code_cell(source=source)))

    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert cell.label is None
    assert cell.label_span is None


def test_duplicate_source_labels_keep_the_winning_exact_span() -> None:
    prefix = "".join(f"#| label: candidate-{index}\n" for index in range(128))
    source = f"{prefix}{'x' * 30_000}\n"
    document = notebook(notebook_payload(code_cell(source=source)))

    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert cell.label == "candidate-127"
    assert decoded_source_segment_text(document, cell.label_span) == "candidate-127"


def test_duplicate_source_languages_use_the_winning_value_and_span() -> None:
    source = "#| language: first\n#| language: second\npass\n"
    document = notebook(notebook_payload(code_cell(source=source)))

    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert cell.language == "second"
    assert cell.language_span is not None
    assert cell.language_span.cell_line == 2
    assert decoded_source_segment_text(document, cell.language_span) == "second"


def test_empty_final_source_language_overrides_an_earlier_value() -> None:
    source = "#| language: python\n#| language:\npass\n"
    document = notebook(notebook_payload(code_cell(source=source)))

    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert cell.language == '<json:"">'
    assert cell.language_span is not None
    assert cell.language_span.cell_line == 2
    assert cell.language_span.start == cell.language_span.end
    assert source_slice(document, cell.language_span) == ""


def test_empty_source_language_at_end_preserves_its_position() -> None:
    source = "#| language:"
    document = notebook(notebook_payload(code_cell(source=source)))

    [cell] = NotebookFrontend().lower((document,)).code_cells

    expected_position = document.text.index(source) + len(source)
    assert cell.language == '<json:"">'
    assert cell.language_span is not None
    assert cell.language_span.cell_line == 1
    assert (cell.language_span.start, cell.language_span.end) == (
        expected_position,
        expected_position,
    )


def test_notebook_code_cell_without_source_keeps_metadata_label() -> None:
    raw_cell = code_cell(metadata={"label": "metadata-only"})
    raw_cell.pop("source")
    document = notebook(notebook_payload(raw_cell))

    result = public_check_documents((document,), config=profile_config())
    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert not any(diagnostic.code == "INP001" for diagnostic in result.diagnostics)
    assert cell.raw is None
    assert cell.label == "metadata-only"
    assert source_slice(document, cell.label_span) == "metadata-only"


def test_reference_engine_is_input_order_deterministic() -> None:
    first = markdown(
        """```{code-cell} python
:label: alpha
pass
```

```{code-cell} julia
:label: alpha
1
```
""",
        "a.md",
    )
    second = markdown(
        """```{code-cell} python
:label: beta
pass
```

```{code-cell} julia
:label: beta
1
```
""",
        "b.md",
    )
    references = markdown("See {ref}`alpha` and {ref}`beta`.\n", "references.md")

    forward = ReferenceEngine().run(QueryHost(MySTFrontend().lower((first, second, references))))
    reverse = ReferenceEngine().run(QueryHost(MySTFrontend().lower((references, second, first))))

    def contract(diagnostics):
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
            for diagnostic in diagnostics
            if diagnostic.code in {"REF005", "REF010"}
        )

    assert contract(forward) == contract(reverse)
    assert [item[0] for item in contract(forward)] == [
        "REF010",
        "REF010",
        "REF005",
        "REF005",
    ]


def test_code_cell_metadata_profile_loads_from_strict_config(tmp_path) -> None:
    path = tmp_path / "scieqlint.toml"
    path.write_text('[profile]\nname = "code-cell-metadata"\n', encoding="utf-8")

    loaded = load_config(path)

    assert loaded.profile.name == "code-cell-metadata"


def test_code_cell_spans_follow_source_metadata_forms() -> None:
    document = markdown(
        """```python
#| label:
pass
```

```{code-cell} python
:label: directive-cell
pass
```

```{code-cell}
pass
```
"""
    )
    snapshot = MySTFrontend().lower((document,))
    plain_cell, directive_cell, missing_language = snapshot.code_cells

    assert plain_cell.label is None
    assert plain_cell.label_span is None
    assert plain_cell.language == "python"
    assert source_slice(document, plain_cell.language_span) == "python"
    assert directive_cell.label == "directive-cell"
    assert source_slice(document, directive_cell.label_span) == "directive-cell"
    assert source_slice(document, directive_cell.language_span) == "python"
    assert missing_language.language is None
    assert missing_language.language_span is None


@pytest.mark.public_regression
def test_public_bare_quarto_bash_fence_resolves_reference_without_execution() -> None:
    bash_document = markdown(
        """```bash
#| label: bash-cell
printf 'not executed\\n'
```

See [bash cell](#bash-cell).
""",
        "bash.md",
    )
    unsupported_document = markdown(
        """```brainfuck
#| label: brainfuck-cell
printf 'not executed\\n'
```

See [brainfuck cell](#brainfuck-cell).
""",
        "unsupported.md",
    )

    bash_result = public_check_documents((bash_document,), config=Config())
    unsupported_result = public_check_documents((unsupported_document,), config=Config())

    assert [diagnostic.code for diagnostic in bash_result.diagnostics] == []
    assert [diagnostic.code for diagnostic in unsupported_result.diagnostics] == ["REF002"]


@pytest.mark.public_regression
def test_public_bare_quarto_bash_fence_resolves_reference_without_execution() -> None:
    bash_document = markdown(
        """```bash
#| label: bash-cell
printf 'not executed\\n'
```

See [bash cell](#bash-cell).
""",
        "bash.md",
    )
    unsupported_document = markdown(
        """```brainfuck
#| label: brainfuck-cell
printf 'not executed\\n'
```

See [brainfuck cell](#brainfuck-cell).
""",
        "unsupported.md",
    )

    bash_result = public_check_documents((bash_document,), config=Config())
    unsupported_result = public_check_documents((unsupported_document,), config=Config())

    assert [diagnostic.code for diagnostic in bash_result.diagnostics] == []
    assert [diagnostic.code for diagnostic in unsupported_result.diagnostics] == ["REF002"]


def test_quarto_code_cell_options_skip_blank_and_comment_preamble() -> None:
    document = markdown(
        """```python

# a comment before the option
#| label: fig-preamble
plot()
```
"""
    )

    [cell] = MySTFrontend().lower((document,)).code_cells

    assert cell.label == "fig-preamble"
    assert source_slice(document, cell.label_span) == "fig-preamble"


def test_notebook_code_cell_options_skip_blank_and_comment_preamble() -> None:
    document = notebook(
        notebook_payload(
            code_cell(source="\n# a comment before the option\n#| label: fig-notebook\npass\n")
        )
    )

    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert cell.label == "fig-notebook"
    assert source_slice(document, cell.label_span) == "fig-notebook"


@pytest.mark.parametrize(
    "source",
    [
        """```{code-cell} python
:label: first
:label: second
pass
```
""",
        """```{code-cell} python
:label:
:label: second
pass
```
""",
        """```{code-cell} python
:name: first
:name: second
pass
```
""",
        """```{python}
#| label: first
#| label: second
pass
```
""",
        """```python
#| label: first
#| label: second
pass
```
""",
        """```python
#| label:
#| label: second
pass
```
""",
    ],
)
def test_duplicate_code_cell_options_use_the_winning_label_span(source: str) -> None:
    document = markdown(source)
    [cell] = MySTFrontend().lower((document,)).code_cells

    assert cell.label == "second"
    assert source_slice(document, cell.label_span) == "second"
    assert cell.label_span is not None
    assert cell.label_span.start == document.text.rindex("second")
