from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.config.model import Config
from scieqlint.graph.export import build_graph
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import LabelSource, ReferenceSource
from scieqlint.scan.latex import LatexScanner
from scieqlint.scan.markdown import MarkdownScanner


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
