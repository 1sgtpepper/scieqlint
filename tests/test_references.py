from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.api import check_documents
from scieqlint.check.references import check_references
from scieqlint.config.model import Config
from scieqlint.diag.model import Severity
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.markdown import MarkdownScanner, _attached_myst_heading_anchor_targets


def _scan(text: str):
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        text,
        DocumentKind.MARKDOWN,
    )
    return MarkdownScanner().scan(document, Config())


def test_missing_reference_is_warning() -> None:
    scan = _scan("See {eq}`missing`.\n")
    diagnostics = check_references(scan.labels, scan.references)
    assert [diagnostic.code for diagnostic in diagnostics] == ["REF002"]
    assert diagnostics[0].severity is Severity.WARNING


def test_duplicate_label_is_error() -> None:
    scan = _scan("$$\nE = m c^2\n$$ {#energy}\n\n$$\nF = m a\n$$ {#energy}\n")
    diagnostics = check_references(scan.labels, scan.references)
    assert [diagnostic.code for diagnostic in diagnostics] == ["REF001"]
    assert diagnostics[0].severity is Severity.ERROR


def test_existing_reference_is_quiet() -> None:
    scan = _scan("$$\nE = m c^2\n$$ {#energy}\n\nSee {eq}`energy`.\n")
    assert check_references(scan.labels, scan.references) == ()


def test_latex_missing_reference_warns() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.tex"),
        "See \\eqref{missing}.\n",
        DocumentKind.LATEX,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]
    assert result.diagnostics[0].detail == r"reference text: \eqref{missing}"


def test_cross_format_reference_is_quiet() -> None:
    latex = SourceDocument.from_text(
        PurePosixPath("paper.tex"),
        "See \\eqref{energy}.\n",
        DocumentKind.LATEX,
    )
    markdown = SourceDocument.from_text(
        PurePosixPath("notes.md"),
        "$$\nE = m c^2\n$$ {#energy}\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([latex, markdown], config=Config())

    assert result.diagnostics == ()


def test_markdown_links_to_myst_heading_anchors_are_not_equation_refs() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "\n".join(
            [
                "(intro)=",
                "# Introduction",
                "",
                "(empty-link-target)=",
                "## Empty link target",
                "",
                "See [](#intro) and [#empty-link-target](#empty-link-target).",
            ]
        ),
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert result.diagnostics == ()


def test_markdown_links_to_comment_bridged_myst_heading_anchors_are_not_equation_refs() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "(intro)=\n<!-- translator note -->\n# Introduction\n\nSee [](#intro).\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert result.diagnostics == ()


def test_orphaned_myst_anchor_does_not_suppress_markdown_missing_reference() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "(loose-anchor)=\nThis paragraph leaves the anchor unattached.\n\nSee [](#loose-anchor).\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]
    assert result.diagnostics[0].detail == "reference text: [](#loose-anchor)"


def test_check_documents_reports_generic_ref_diagnostics_distinct_from_equation_refs() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "\n".join(
            [
                "(intro)=",
                "# Introduction",
                "",
                "(intro)=",
                "## Duplicate Introduction",
                "",
                "See {ref}`intro`, {ref}`missing`, and {eq}`eq-missing`.",
            ]
        ),
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "REF005",
        "REF004",
        "REF002",
    ]


def test_generated_output_with_dropped_myst_anchor_and_preserved_ref_warns() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("translated/lecture.md"),
        "## A Workaround\n\nSee {ref}`jax_at_workaround`.\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [(diagnostic.code, diagnostic.detail) for diagnostic in result.diagnostics] == [
        ("REF004", "reference text: {ref}`jax_at_workaround`")
    ]


def test_myst_anchor_inside_code_fence_does_not_suppress_markdown_missing_reference() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "```text\n(code-anchor)=\n# Code heading\n```\n\nSee [](#code-anchor).\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]


def test_lone_myst_anchor_has_no_attached_heading_target() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "(lonely)=",
        DocumentKind.MARKDOWN,
    )

    assert _attached_myst_heading_anchor_targets(document) == frozenset()
