from __future__ import annotations

from pathlib import Path, PurePosixPath

from scieqlint.config.model import Config, ScannerConfig
from scieqlint.io.source import DocumentKind, SourceDocument
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


def test_display_math_is_not_closed_by_delimiter_in_multibacktick_code() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\na = a\n``$$``\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]


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
