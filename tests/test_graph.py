from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from scieqlint.api import check_documents, graph_documents
from scieqlint.config.model import Config
from scieqlint.diag.model import Diagnostic, Severity, SourceSpan
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.graph.export import build_graph
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import LabelSource, ReferenceSource
from scieqlint.scan.latex import LatexScanner
from scieqlint.scan.markdown import MarkdownScanner


@pytest.mark.public_regression
def test_graph_uses_only_tokenized_markdown_references() -> None:
    source = (
        "Literal \\{eq}`escaped-role`.\n"
        "Literal \\[Eq.](#escaped-link).\n"
        "![equation](#image-target)\n"
        "[site](https://example.invalid/{eq}`destination-target`)\n"
        '[site](https://example.invalid/ "{eq}`title-target`")\n'
        "[See {eq}`active-label`](https://example.invalid/)\n"
    )
    document = _markdown("references.md", source)

    result = check_documents([document], config=Config())
    graph = graph_documents([document], config=Config())

    target_start = source.index("active-label")
    target_end = target_start + len("active-label")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert result.exit_code() == 0
    assert result.diagnostics == (
        Diagnostic(
            code="REF002",
            severity=Severity.WARNING,
            message="equation reference target not found: active-label",
            span=SourceSpan(
                path=PurePosixPath("references.md"),
                start=target_start,
                end=target_end,
                line=6,
                col=11,
                end_line=6,
                end_col=22,
            ),
            detail="reference text: {eq}`active-label`",
            rule="references",
        ),
    )
    assert [
        (node.id, node.kind, node.label, node.source, node.span.line, node.span.col)
        for node in graph.nodes
    ] == [
        (
            f"ref:references.md:{target_start}",
            "reference",
            "active-label",
            ReferenceSource.MYST_EQ_ROLE.value,
            6,
            11,
        )
    ]
    assert [
        (edge.source, edge.target, edge.target_label, edge.raw, edge.source_kind)
        for edge in graph.edges
    ] == [
        (
            f"ref:references.md:{target_start}",
            "label:active-label",
            "active-label",
            "{eq}`active-label`",
            ReferenceSource.MYST_EQ_ROLE.value,
        )
    ]


@pytest.mark.public_regression
def test_link_metadata_does_not_claim_later_live_math() -> None:
    source = (
        '[site](https://example.invalid/ "\n'
        "$$\nmetadata = metadata\n"
        '")\n'
        "$$\ny = y\n$$\n"
        "See {eq}`active`.\n"
    )
    document = _markdown("paper.md", source)

    result = check_documents([document], config=Config())
    graph = graph_documents([document], config=Config())

    target_start = source.index("active")
    target_end = target_start + len("active")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 1
    assert result.config_path is None
    assert result.exit_code() == 0
    assert result.diagnostics == (
        Diagnostic(
            code="REF002",
            severity=Severity.WARNING,
            message="equation reference target not found: active",
            span=SourceSpan(
                path=PurePosixPath("paper.md"),
                start=target_start,
                end=target_end,
                line=8,
                col=10,
                end_line=8,
                end_col=15,
            ),
            detail="reference text: {eq}`active`",
            rule="references",
        ),
    )
    assert [
        (node.id, node.kind, node.label, node.source, node.span.line, node.span.col)
        for node in graph.nodes
    ] == [
        (
            f"ref:paper.md:{target_start}",
            "reference",
            "active",
            ReferenceSource.MYST_EQ_ROLE.value,
            8,
            10,
        )
    ]
    assert [
        (edge.source, edge.target, edge.target_label, edge.raw, edge.source_kind)
        for edge in graph.edges
    ] == [
        (
            f"ref:paper.md:{target_start}",
            "label:active",
            "active",
            "{eq}`active`",
            ReferenceSource.MYST_EQ_ROLE.value,
        )
    ]


@pytest.mark.public_regression
def test_markdown_link_labels_do_not_cross_block_boundaries() -> None:
    source = (
        "[soft\ncontinued](#soft)\n"
        "[blank\n\ncontinued](#blank)\n"
        "[fence\n```text\ncode\n```\ncontinued](#fence)\n"
        "See {eq}`control`.\n"
    )
    document = _markdown("paper.md", source)

    result = check_documents([document], config=Config())
    graph = graph_documents([document], config=Config())

    soft_start = source.index("#soft") + 1
    control_start = source.index("control")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert result.config_path is None
    assert result.exit_code() == 0
    assert result.diagnostics == (
        Diagnostic(
            code="REF002",
            severity=Severity.WARNING,
            message="equation reference target not found: soft",
            span=SourceSpan(
                path=PurePosixPath("paper.md"),
                start=soft_start,
                end=soft_start + len("soft"),
                line=2,
                col=13,
                end_line=2,
                end_col=16,
            ),
            detail="reference text: [soft\ncontinued](#soft)",
            rule="references",
        ),
        Diagnostic(
            code="REF002",
            severity=Severity.WARNING,
            message="equation reference target not found: control",
            span=SourceSpan(
                path=PurePosixPath("paper.md"),
                start=control_start,
                end=control_start + len("control"),
                line=11,
                col=10,
                end_line=11,
                end_col=16,
            ),
            detail="reference text: {eq}`control`",
            rule="references",
        ),
    )
    assert [
        (node.id, node.kind, node.label, node.source, node.span.line, node.span.col)
        for node in graph.nodes
    ] == [
        (
            f"ref:paper.md:{soft_start}",
            "reference",
            "soft",
            ReferenceSource.MARKDOWN_ANCHOR.value,
            2,
            13,
        ),
        (
            f"ref:paper.md:{control_start}",
            "reference",
            "control",
            ReferenceSource.MYST_EQ_ROLE.value,
            11,
            10,
        ),
    ]
    assert [
        (edge.source, edge.target, edge.target_label, edge.raw, edge.source_kind)
        for edge in graph.edges
    ] == [
        (
            f"ref:paper.md:{soft_start}",
            "label:soft",
            "soft",
            "[soft\ncontinued](#soft)",
            ReferenceSource.MARKDOWN_ANCHOR.value,
        ),
        (
            f"ref:paper.md:{control_start}",
            "label:control",
            "control",
            "{eq}`control`",
            ReferenceSource.MYST_EQ_ROLE.value,
        ),
    ]


@pytest.mark.public_regression
def test_markdown_link_to_fenced_target_is_not_an_equation_reference() -> None:
    source = (
        "(tip)=\n"
        "```{note}\n"
        "Keep this note.\n"
        "```\n\n"
        "See {ref}`tip` and [the note](#tip).\n"
        "See [missing](#missing).\n"
    )
    document = _markdown("paper.md", source)

    result = check_documents([document], config=Config())
    graph = graph_documents([document], config=Config())

    target_start = source.index("#missing") + 1
    target_end = target_start + len("missing")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert result.exit_code() == 0
    assert result.diagnostics == (
        Diagnostic(
            code="REF002",
            severity=Severity.WARNING,
            message="equation reference target not found: missing",
            span=SourceSpan(
                path=PurePosixPath("paper.md"),
                start=target_start,
                end=target_end,
                line=7,
                col=16,
                end_line=7,
                end_col=22,
            ),
            detail="reference text: [missing](#missing)",
            rule="references",
        ),
    )
    assert [(node.kind, node.label) for node in graph.nodes] == [("reference", "missing")]
    assert [(edge.target, edge.target_label) for edge in graph.edges] == [
        ("label:missing", "missing")
    ]


def test_link_metadata_does_not_create_a_myst_heading_target() -> None:
    source = (
        "[x](\n"
        "(hidden)=\n"
        ")\n"
        "(real)=\n"
        "# Heading\n\n"
        "See [good](#real) and [bad](#hidden).\n"
    )
    document = _markdown("paper.md", source)

    result = check_documents([document], config=Config())
    graph = graph_documents([document], config=Config())
    frontend = MySTFrontend().lower((document,))

    target_start = source.index("#hidden") + 1
    target_end = target_start + len("hidden")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert result.config_path is None
    assert result.exit_code() == 0
    assert result.diagnostics == (
        Diagnostic(
            code="REF002",
            severity=Severity.WARNING,
            message="equation reference target not found: hidden",
            span=SourceSpan(
                path=PurePosixPath("paper.md"),
                start=target_start,
                end=target_end,
                line=7,
                col=30,
                end_line=7,
                end_col=35,
            ),
            detail="reference text: [bad](#hidden)",
            rule="references",
        ),
    )
    assert [heading.text for heading in frontend.headings] == ["Heading"]
    assert [anchor.label for anchor in frontend.target_anchors] == ["real"]
    assert [
        (node.id, node.kind, node.label, node.source, node.span.line, node.span.col)
        for node in graph.nodes
    ] == [
        (
            f"ref:paper.md:{target_start}",
            "reference",
            "hidden",
            ReferenceSource.MARKDOWN_ANCHOR.value,
            7,
            30,
        )
    ]
    assert [
        (edge.source, edge.target, edge.target_label, edge.raw, edge.source_kind)
        for edge in graph.edges
    ] == [
        (
            f"ref:paper.md:{target_start}",
            "label:hidden",
            "hidden",
            "[bad](#hidden)",
            ReferenceSource.MARKDOWN_ANCHOR.value,
        )
    ]


def test_graph_nodes_cover_markdown_myst_and_latex_labels() -> None:
    markdown = _markdown(
        "paper.md",
        "$$\nE = m c^2\n$$ {#eq-md}\n\n```{math}\n:label: eq-myst\nF = m a\n```\n",
    )
    latex = _latex("\\begin{equation}\n\\label{eq:tex}\nE = m c^2\n\\end{equation}\n")
    markdown_scan = MarkdownScanner().scan(markdown, Config())
    latex_scan = LatexScanner().scan(latex, Config())

    graph = build_graph(
        (*markdown_scan.labels, *latex_scan.labels),
        (),
    )

    assert [(node.kind, node.label, node.source) for node in graph.nodes] == [
        ("equation", "eq-md", LabelSource.MARKDOWN_ANCHOR.value),
        ("equation", "eq-myst", LabelSource.MYST_DIRECTIVE_LABEL.value),
        ("equation", "eq:tex", LabelSource.LATEX_LABEL.value),
    ]
    assert len({node.id for node in graph.nodes}) == 3


def test_graph_edges_cover_supported_reference_forms() -> None:
    markdown = _markdown(
        "paper.md",
        "See [Eq.](#eq-md), {eq}`eq-myst`, and {numref}`Equation <eq-num>`.\n",
    )
    latex = _latex("See \\eqref{eq:tex} and \\ref{eq:force}.\n")
    markdown_scan = MarkdownScanner().scan(markdown, Config())
    latex_scan = LatexScanner().scan(latex, Config())

    graph = build_graph(
        (),
        (*markdown_scan.references, *latex_scan.references),
    )

    assert [
        (edge.target, edge.kind, edge.target_label, edge.raw, edge.source_kind)
        for edge in graph.edges
    ] == [
        (
            "label:eq-md",
            "references",
            "eq-md",
            "[Eq.](#eq-md)",
            ReferenceSource.MARKDOWN_ANCHOR.value,
        ),
        (
            "label:eq-myst",
            "references",
            "eq-myst",
            "{eq}`eq-myst`",
            ReferenceSource.MYST_EQ_ROLE.value,
        ),
        (
            "label:eq-num",
            "references",
            "eq-num",
            "{numref}`Equation <eq-num>`",
            ReferenceSource.MYST_NUMREF_ROLE.value,
        ),
        (
            "label:eq:tex",
            "references",
            "eq:tex",
            "\\eqref{eq:tex}",
            ReferenceSource.LATEX_EQREF.value,
        ),
        (
            "label:eq:force",
            "references",
            "eq:force",
            "\\ref{eq:force}",
            ReferenceSource.LATEX_REF.value,
        ),
    ]
    assert [node.kind for node in graph.nodes] == ["reference"] * 5


def test_graph_edges_resolve_unique_label_targets() -> None:
    markdown = _markdown(
        "paper.md",
        "$$\na = a\n$$ {#only}\n\nSee {eq}`only`.\n",
    )
    scan = MarkdownScanner().scan(markdown, Config())

    graph = build_graph(scan.labels, scan.references)

    equation_ids = [node.id for node in graph.nodes if node.kind == "equation"]
    assert len(equation_ids) == 1
    assert [(edge.target, edge.target_label) for edge in graph.edges] == [(equation_ids[0], "only")]


def test_duplicate_label_nodes_have_stable_unique_ids_and_ambiguous_edges() -> None:
    markdown = _markdown(
        "paper.md",
        "$$\na = a\n$$ {#dup}\n\n$$\nb = b\n$$ {#dup}\n\nSee {eq}`dup`.\n",
    )
    scan = MarkdownScanner().scan(markdown, Config())
    graph = build_graph(tuple(reversed(scan.labels)), scan.references)

    equation_nodes = [node for node in graph.nodes if node.kind == "equation"]
    assert [node.label for node in equation_nodes] == ["dup", "dup"]
    assert len({node.id for node in equation_nodes}) == 2
    assert [(edge.target, edge.target_label) for edge in graph.edges] == [("label:dup", "dup")]


def test_graph_output_is_stably_sorted() -> None:
    markdown = _markdown(
        "paper.md",
        "$$\na = a\n$$ {#z}\n\n$$\nb = b\n$$ {#a}\n\nSee {eq}`z` and {eq}`a`.\n",
    )
    scan = MarkdownScanner().scan(markdown, Config())
    reversed_labels = tuple(reversed(scan.labels))
    reversed_references = tuple(reversed(scan.references))

    graph = build_graph(reversed_labels, reversed_references)

    assert [node.id for node in graph.nodes] == [
        "eq:paper.md:14",
        "eq:paper.md:32",
        "ref:paper.md:45",
        "ref:paper.md:57",
    ]
    assert [(edge.source, edge.target) for edge in graph.edges] == [
        ("ref:paper.md:45", "eq:paper.md:14"),
        ("ref:paper.md:57", "eq:paper.md:32"),
    ]


def _markdown(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath(path),
        text,
        DocumentKind.MARKDOWN,
    )


def _latex(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("paper.tex"),
        text,
        DocumentKind.LATEX,
    )
