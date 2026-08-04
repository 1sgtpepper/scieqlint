from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.api import check_documents
from scieqlint.config.model import Config, ScannerConfig
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import LabelSource, MathContainer, ReferenceSource
from scieqlint.scan.markdown import MarkdownScanner


def test_scans_myst_math_directive_label_and_eq_role() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "```{math}\n:label: energy\nE = m c^2\n```\n\nSee {eq}`energy`.\n",
        DocumentKind.MARKDOWN,
    )
    result = MarkdownScanner().scan(document, Config())
    assert result.blocks[0].container is MathContainer.MARKDOWN_FENCE
    assert [(label.label, label.source) for label in result.labels] == [
        ("energy", LabelSource.MYST_DIRECTIVE_LABEL)
    ]
    assert [(ref.target, ref.source) for ref in result.references] == [
        ("energy", ReferenceSource.MYST_EQ_ROLE)
    ]


def test_math_fence_scanning_can_be_disabled() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "```{math}\n:label: energy\nE = m c^2\n```\n",
        DocumentKind.MARKDOWN,
    )
    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(math_fences=False)),
    )
    assert result.blocks == ()
    assert result.labels == ()


def test_unterminated_math_fence_emits_scan_warning() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "```{math}\na = a\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]
    assert result.diagnostics[0].span.line == 1
    assert result.diagnostics[0].rule == "scanner"


def test_math_container_spans_start_at_first_nonblank_body_line() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\n\nx = x\n$$\n\n```math\n\ny = y\n```\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [(block.container, block.text, block.span.line) for block in result.blocks] == [
        (MathContainer.MARKDOWN_DISPLAY, "x = x", 3),
        (MathContainer.MARKDOWN_FENCE, "y = y", 8),
    ]


def test_late_myst_math_label_is_not_an_equation_target() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "```{math}\nx = x\n:label: ghost\n```\nSee {eq}`ghost`.\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]


def test_empty_myst_equation_role_is_not_a_reference() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "See {eq}`   `.\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.references == ()


def test_blank_line_does_not_end_myst_math_label_prefix() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "```{math}\n:label: first\n\n:label: second\nx = x\n```\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [label.label for label in result.labels] == ["first", "second"]


def test_malformed_myst_option_ends_the_math_label_prefix() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "```{math}\n:not-an-option\n:label: ghost\nx = x\n```\n",
        DocumentKind.MARKDOWN,
    )

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert legacy.labels == ()
    assert frontend.equation_labels == ()
