from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.api import check_documents, graph_documents
from scieqlint.config.model import Config
from scieqlint.io.source import DocumentKind, SourceDocument


def document() -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("visibility.md"),
        "$$\nx = 1\n$$ {#eq-one}\n\n{eq}`eq-one`\n",
        DocumentKind.MARKDOWN,
    )


def test_public_visibility_projection_keeps_visible_and_nonvisible_targets_distinct() -> None:
    source = document()

    visible = check_documents((source,), config=Config())
    hidden = check_documents(
        (source,),
        config=Config(),
        project_visibility={"visibility.md": "hidden"},
    )
    excluded = check_documents(
        (source,),
        config=Config(),
        project_visibility={"visibility.md": "excluded"},
    )

    assert not any(item.code == "REF008" for item in visible.diagnostics)
    assert [item.code for item in hidden.diagnostics].count("REF008") == 1
    assert [item.code for item in excluded.diagnostics].count("REF008") == 1


def test_public_excluded_visibility_removes_the_document_from_the_graph() -> None:
    source = document()

    visible = graph_documents((source,), config=Config())
    excluded = graph_documents(
        (source,),
        config=Config(),
        project_visibility={"visibility.md": "excluded"},
    )

    assert visible.nodes
    assert visible.edges
    assert excluded.nodes == ()
    assert excluded.edges == ()
