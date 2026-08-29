from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

from scieqlint.api import check_documents as public_check_documents
from scieqlint.app import _profile_snapshot
from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    ProfileConfig,
)
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.facts.structure import CodeCellFact
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.frontend.notebook import NotebookFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
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
        profile=ProfileConfig(name="notebook-crossrefs"),
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


def source_segment_text(document: SourceDocument, span) -> str:
    assert span is not None
    assert span.segments
    return "".join(
        document.text[start:end] for segment in span.segments for start, end in segment.ranges
    )


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
        ("cell", None, "code-cell label and normalized label must both be present or absent"),
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
    [cell] = [fact for fact in snapshot.code_cells if fact.document_id == nb.path.as_posix()]

    assert cell.label == "cell-notebook"
    assert cell.normalized_label == "cell-notebook"
    assert cell.language == "python"
    assert cell.label_span is not None
    assert source_slice(nb, cell.label_span) == "cell-notebook"
    assert cell.label_span.cell == 0
    assert ReferenceEngine().run(QueryHost(snapshot)) == ()


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
    plain_cell, directive_cell, _ = snapshot.code_cells

    assert plain_cell.label is None
    assert plain_cell.label_span is None
    assert plain_cell.language == "python"
    assert directive_cell.label == "directive-cell"
    assert source_slice(document, directive_cell.label_span) == "directive-cell"


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
    ],
)
def test_duplicate_code_cell_options_use_the_winning_label_span(source: str) -> None:
    document = markdown(source)
    [cell] = MySTFrontend().lower((document,)).code_cells

    assert cell.label == "second"
    assert source_slice(document, cell.label_span) == "second"
    assert cell.label_span is not None
    assert cell.label_span.start == document.text.rindex("second")
