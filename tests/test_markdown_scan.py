from __future__ import annotations

from pathlib import Path, PurePosixPath

from scieqlint.api import check_documents
from scieqlint.config.model import ChecksConfig, Config, ScannerConfig, SymbolsConfig
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.markdown import code_fence_ranges
from scieqlint.scan.base import (
    MathContainer,
    ReferenceSource,
    SymbolDirectiveSource,
)
from scieqlint.scan.markdown import MarkdownScanner


def test_scans_display_math_label_and_markdown_reference() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\nE = m c^2\n$$ {#eq-energy}\n\nSee [Eq.](#eq-energy).\n",
        DocumentKind.MARKDOWN,
    )
    result = MarkdownScanner().scan(document, Config())
    assert len(result.blocks) == 1
    assert result.blocks[0].container is MathContainer.MARKDOWN_DISPLAY
    assert result.blocks[0].span.line == 2
    assert [label.label for label in result.labels] == ["eq-energy"]
    assert [(ref.target, ref.source) for ref in result.references] == [
        ("eq-energy", ReferenceSource.MARKDOWN_ANCHOR),
    ]


def test_inline_math_scans_only_when_enabled() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Inline $(a+b)^2 = a^2 + b^2$ example.\n",
        DocumentKind.MARKDOWN,
    )
    assert MarkdownScanner().scan(document, Config()).blocks == ()

    config = Config(scanner=ScannerConfig(inline_math=True))
    result = MarkdownScanner().scan(document, config)

    assert len(result.blocks) == 1
    assert result.blocks[0].container is MathContainer.MARKDOWN_INLINE


def test_inline_dollar_math_span_tracks_trimmed_source_body() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $  x = y  $.\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    block = result.blocks[0]
    assert block.text == "x = y"
    assert block.span.col == 9
    assert document.text[block.span.start : block.span.end] == block.text


def test_inline_dollar_math_span_preserves_tabs_and_combining_unicode() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $\t x\u0301 = y \t $.\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    block = result.blocks[0]
    assert block.text == "x\u0301 = y"
    assert document.text[block.span.start : block.span.end] == block.text


def test_inline_dollar_math_whitespace_only_body_is_not_a_fact() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $ \t $ after.\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert result.blocks == ()


def test_inline_dollar_math_symbol_diagnostics_use_trimmed_source_columns() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $  x = y  $.\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents(
        [document],
        config=Config(
            scanner=ScannerConfig(inline_math=True),
            checks=ChecksConfig(symbols=SymbolsConfig(enabled=True)),
        ),
    )

    assert [
        (diagnostic.code, diagnostic.detail, diagnostic.span.col)
        for diagnostic in result.diagnostics
        if diagnostic.span is not None
    ] == [("SYM001", "x", 9), ("SYM001", "y", 13)]


def test_inline_math_ignores_code_spans_and_non_math_fences() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        'Code span `$not = math$`.\n\n```python\nalso = "$not_math$"\n```\n',
        DocumentKind.MARKDOWN,
    )
    config = Config(scanner=ScannerConfig(inline_math=True))

    result = MarkdownScanner().scan(document, config)

    assert result.blocks == ()


def test_unterminated_display_math_emits_scan_warning() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\na = a\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]
    assert result.diagnostics[0].span.line == 1
    assert result.diagnostics[0].rule == "scanner"


def test_closed_display_math_does_not_emit_scan_warning() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\na = a\n$$\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert len(result.blocks) == 1
    assert result.diagnostics == ()


def test_dollar_math_respects_escape_and_block_boundaries() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        r"Literal \$x=x+1$." + "\n" + "Prose $$x=x+1$$ tail.\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert result.blocks == ()
    assert result.diagnostics == ()


def test_display_dollar_math_requires_a_line_boundary_and_allows_indent() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "  $$\nx = x\n  $$\n\nprose $$y = y$$\n\n$$$z = z$$$\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [block.text for block in result.blocks] == ["x = x"]
    assert result.diagnostics == ()


def test_inline_dollar_math_requires_outer_text_boundaries() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "word$x = x$ and $x = x$word\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert result.blocks == ()


def test_inline_dollar_math_skips_escaped_closers_and_keeps_even_slashes_active() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        r"$x=\$3=x$ and \\$y$.",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert [block.text for block in result.blocks] == [r"x=\$3=x", "y"]


def test_dollar_tail_accepts_only_a_complete_label_suffix() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\nx = x\n$$ prose (ghost)\n\n$$\ny = y\n$$ {#real}\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [label.label for label in result.labels] == ["real"]


def test_display_delimiter_in_inline_code_does_not_emit_scan_warning() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Use `$$` and ``$$`` literally.\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert result.diagnostics == ()


def test_display_delimiter_in_non_math_fence_does_not_emit_scan_warning() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        '```python\nprint("$$")\n```\n',
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert result.diagnostics == ()


def test_display_math_is_not_closed_by_delimiter_in_inline_code() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\na = a\n`$$`\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]


def test_legacy_and_frontend_display_math_ignore_inline_code_delimiters() -> None:
    text = "$$\nleft\n`$$`\nright\n$$\n"
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [block.text for block in legacy.blocks] == ["left\n`$$`\nright"]
    assert [math.body for math in frontend.display_math] == ["left\n`$$`\nright"]
    assert frontend.display_math[0].span is not None
    assert (legacy.blocks[0].span.start, legacy.blocks[0].span.end) == (
        frontend.display_math[0].span.start,
        frontend.display_math[0].span.end,
    )
    assert legacy.diagnostics == ()


def test_legacy_and_frontend_display_math_ignore_tilde_fence_delimiters() -> None:
    text = "~~~\n$$\ninside = inside\n$$\n~~~\n\n$$\noutside = outside\n$$\n"
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [block.text for block in legacy.blocks] == ["outside = outside"]
    assert [math.body for math in frontend.display_math] == ["outside = outside"]
    assert frontend.display_math[0].span is not None
    assert (legacy.blocks[0].span.start, legacy.blocks[0].span.end) == (
        frontend.display_math[0].span.start,
        frontend.display_math[0].span.end,
    )
    assert legacy.diagnostics == ()


def test_legacy_and_frontend_display_math_ignore_unclosed_tilde_fences() -> None:
    text = "~~~\n$$\ninside = inside\n$$\n"
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert legacy.blocks == ()
    assert frontend.display_math == ()
    assert legacy.diagnostics == ()


def test_display_math_is_not_closed_by_delimiter_in_multibacktick_code() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\na = a\n``$$``\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]


def test_inline_math_stays_opaque_inside_a_longer_backtick_span() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "``$x$ `inner` tail``\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert result.blocks == ()
    assert result.diagnostics == ()
    assert MySTFrontend().lower((document,)).inline_math == ()


def test_inline_math_stays_opaque_inside_a_multiline_backtick_span() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Use ``foo\n$x$\nbar`` end.\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert result.blocks == ()
    assert result.diagnostics == ()


def test_fence_closer_allows_at_most_three_leading_spaces() -> None:
    for spaces in range(4):
        text = f"```\ninside\n{' ' * spaces}```\noutside\n"
        close_start = text.index("```", text.index("inside") + len("inside"))
        assert code_fence_ranges(text) == ((0, close_start + 4),)

    text = "```\ninside\n  ``` \t\noutside\n"
    assert code_fence_ranges(text) == ((0, text.index("outside")),)

    text = "```\ninside\n    ```\noutside\n```\n"
    assert code_fence_ranges(text) == ((0, len(text)),)


def test_fence_closer_requires_the_marker_type_and_length() -> None:
    text = "````\ninside\n```\n~~~\n`````\noutside\n"

    close_start = text.index("`````")
    assert code_fence_ranges(text) == ((0, close_start + 6),)


def test_backtick_fence_info_string_cannot_contain_a_backtick() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "```info`\n$$\nx = x\n$$\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [block.text for block in result.blocks] == ["x = x"]
    assert result.diagnostics == ()


def test_markdown_symbol_directive_fixture_is_extracted() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("tests/fixtures/good/symbol_directives.md"),
        Path("tests/fixtures/good/symbol_directives.md").read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [
        (directive.symbol, directive.description, directive.dimension)
        for directive in result.symbol_directives
    ] == [("E", "energy", "M L^2 T^-2")]
    assert result.symbol_directives[0].source is SymbolDirectiveSource.MARKDOWN_COMMENT
    span = result.symbol_directives[0].span
    assert document.text[span.start : span.end] == "E"
    assert result.diagnostics == ()


def test_malformed_markdown_symbol_directive_warns_and_code_fence_is_ignored() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("tests/fixtures/bad/symbol_directives_bad.md"),
        Path("tests/fixtures/bad/symbol_directives_bad.md").read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.symbol_directives == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN010"]


def test_markdown_symbol_directive_dimension_is_optional() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<!-- scieqlint-symbol: n = sample count -->\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [
        (directive.symbol, directive.description, directive.dimension)
        for directive in result.symbol_directives
    ] == [("n", "sample count", None)]
