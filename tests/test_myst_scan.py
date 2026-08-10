from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from scieqlint.api import check_documents
from scieqlint.config.model import ChecksConfig, Config, ScannerConfig, SymbolsConfig
from scieqlint.diag.model import Diagnostic, Severity, SourceSpan
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


def test_myst_inline_dollar_math_span_tracks_trimmed_source_body() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $  x = y  $.\n",
        DocumentKind.MARKDOWN,
    )

    fact = MySTFrontend().lower((document,)).inline_math[0]

    assert fact.body == "x = y"
    assert fact.span.col == 9
    assert document.text[fact.span.start : fact.span.end] == fact.body


def test_myst_inline_dollar_math_span_preserves_tabs_and_combining_unicode() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $\t x\u0301 = y \t $.\n",
        DocumentKind.MARKDOWN,
    )

    fact = MySTFrontend().lower((document,)).inline_math[0]

    assert fact.body == "x\u0301 = y"
    assert document.text[fact.span.start : fact.span.end] == fact.body


def test_myst_inline_dollar_math_whitespace_only_body_is_not_a_fact() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $ \t $ after.\n",
        DocumentKind.MARKDOWN,
    )

    assert MySTFrontend().lower((document,)).inline_math == ()


def test_display_dollar_math_whitespace_only_body_is_not_a_fact() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\n \t \n$$\n",
        DocumentKind.MARKDOWN,
    )

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))
    result = check_documents([document], config=Config())

    assert legacy.blocks == ()
    assert legacy.diagnostics == ()
    assert frontend.display_math == ()
    assert result.math_blocks_checked == 0
    assert result.diagnostics == ()


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


def test_myst_dollar_math_respects_escape_and_block_boundaries() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Literal \\$x=x+1$.\nProse $$x=x+1$$ tail.\n",
        DocumentKind.MARKDOWN,
    )

    snapshot = MySTFrontend().lower((document,))

    assert snapshot.display_math == ()
    assert snapshot.inline_math == ()


@pytest.mark.public_regression
def test_public_dollar_math_boundaries_ignore_escaped_and_prose_delimiters() -> None:
    source = "Literal \\$x=x+1$.\nProse $$x=x+1$$ tail.\n\n$$\ny = y\n$$\n"
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        source,
        DocumentKind.MARKDOWN,
    )

    result = check_documents(
        [document],
        config=Config(
            scanner=ScannerConfig(inline_math=True),
            checks=ChecksConfig(symbols=SymbolsConfig(enabled=True)),
        ),
    )

    symbol_start = source.index("y = y")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 1
    assert result.exit_code() == 0
    assert result.diagnostics == (
        Diagnostic(
            code="SYM001",
            severity=Severity.WARNING,
            message="undefined symbol: y",
            span=SourceSpan(
                path=PurePosixPath("paper.md"),
                start=symbol_start,
                end=symbol_start + 1,
                line=5,
                col=1,
                end_line=5,
                end_col=1,
            ),
            detail="y",
            rule="symbols",
        ),
    )
    span = result.diagnostics[0].span
    assert span is not None
    assert source[span.start : span.end] == "y"


def test_myst_display_dollar_math_accepts_indentation_but_not_prose_prefix() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "  $$\nx = x\n  $$\n\nprose $$y = y$$\n",
        DocumentKind.MARKDOWN,
    )

    snapshot = MySTFrontend().lower((document,))

    assert [fact.body for fact in snapshot.display_math] == ["x = x"]


def test_myst_dollar_tail_requires_a_complete_label_suffix() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\nx = x\n$$ prose (ghost)\nmore\n$$ {#real}\n",
        DocumentKind.MARKDOWN,
    )

    snapshot = MySTFrontend().lower((document,))

    assert [label.label for label in snapshot.equation_labels] == ["real"]


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


def test_frontend_inline_math_span_tracks_trimmed_source_body() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $  x = y  $.\n",
        DocumentKind.MARKDOWN,
    )

    fact = MySTFrontend().lower((document,)).inline_math[0]

    assert fact.body == "x = y"
    assert fact.span.col == 9
    assert document.text[fact.span.start : fact.span.end] == "x = y"


def test_frontend_inline_math_whitespace_only_body_is_not_a_fact() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $ \t $.\n",
        DocumentKind.MARKDOWN,
    )

    assert MySTFrontend().lower((document,)).inline_math == ()


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
