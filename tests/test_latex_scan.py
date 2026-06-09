from __future__ import annotations

from pathlib import Path, PurePosixPath

from scieqlint.config.model import Config
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import (
    LabelSource,
    MathContainer,
    ReferenceSource,
    SymbolDirectiveSource,
)
from scieqlint.scan.latex import LatexScanner


def test_latex_equation_environment_is_extracted() -> None:
    result = LatexScanner().scan(
        _document("\\begin{equation}\nE = m c^2\n\\end{equation}\n"),
        Config(),
    )

    assert len(result.blocks) == 1
    assert result.blocks[0].text == "E = m c^2"
    assert result.blocks[0].container is MathContainer.LATEX_EQUATION
    assert result.blocks[0].span.line == 2


def test_latex_align_environment_splits_rows_and_removes_alignment_markers() -> None:
    result = LatexScanner().scan(
        _document("\\begin{align}\nE &= m c^2 \\\\[3pt]\nF &= m a\n\\end{align}\n"),
        Config(),
    )

    assert [block.text for block in result.blocks] == ["E = m c^2", "F = m a"]
    assert [block.container for block in result.blocks] == [
        MathContainer.LATEX_ALIGN,
        MathContainer.LATEX_ALIGN,
    ]
    assert result.diagnostics == ()


def test_latex_display_delimiters_are_extracted() -> None:
    result = LatexScanner().scan(
        _document("\\[\na = a\n\\]\n\n$$\nb = b\n$$\n"),
        Config(),
    )

    assert [block.text for block in result.blocks] == ["a = a", "b = b"]
    assert [block.container for block in result.blocks] == [
        MathContainer.LATEX_DISPLAY,
        MathContainer.LATEX_DISPLAY,
    ]


def test_latex_scanner_ignores_comments_and_verbatim() -> None:
    result = LatexScanner().scan(
        _document(
            "% \\begin{equation}\n"
            "\\begin{verbatim}\n"
            "\\[ not = math \\]\n"
            "\\end{verbatim}\n"
            "\\begin{equation}\n"
            "a = a % trailing comment\n"
            "\\end{equation}\n"
        ),
        Config(),
    )

    assert [block.text for block in result.blocks] == ["a = a"]
    assert result.diagnostics == ()


def test_latex_labels_and_references_are_extracted() -> None:
    document = _document(
        "\\begin{equation}\n"
        "  \\label{eq:energy}\n"
        "E = m c^2\n"
        "\\end{equation}\n"
        "See \\eqref{eq:energy} and \\ref{eq:force}.\n"
    )
    result = LatexScanner().scan(document, Config())

    assert len(result.labels) == 1
    assert result.labels[0].label == "eq:energy"
    assert result.labels[0].source is LabelSource.LATEX_LABEL
    label_span = result.labels[0].span
    assert document.text[label_span.start : label_span.end] == "eq:energy"
    assert [(ref.target, ref.source) for ref in result.references] == [
        ("eq:energy", ReferenceSource.LATEX_EQREF),
        ("eq:force", ReferenceSource.LATEX_REF),
    ]


def test_latex_labels_in_comments_are_ignored() -> None:
    result = LatexScanner().scan(
        _document(
            "\\begin{equation}\nE = m c^2 % \\label{commented}\n\\label{real}\n\\end{equation}\n"
        ),
        Config(),
    )

    assert [label.label for label in result.labels] == ["real"]


def test_latex_unterminated_equation_warns() -> None:
    result = LatexScanner().scan(_document("\\begin{equation}\na = a\n"), Config())

    assert result.blocks == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]
    assert result.diagnostics[0].span.line == 1


def test_latex_unterminated_display_delimiter_warns() -> None:
    result = LatexScanner().scan(_document("\\[\na = a\n"), Config())

    assert result.blocks == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]


def test_latex_symbol_directive_fixture_is_extracted() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("tests/fixtures/good/symbol_directives.tex"),
        Path("tests/fixtures/good/symbol_directives.tex").read_text(encoding="utf-8"),
        DocumentKind.LATEX,
    )

    result = LatexScanner().scan(document, Config())

    assert [
        (directive.symbol, directive.description, directive.dimension)
        for directive in result.symbol_directives
    ] == [("F", "force", "M L T^-2")]
    assert result.symbol_directives[0].source is SymbolDirectiveSource.LATEX_COMMENT
    span = result.symbol_directives[0].span
    assert document.text[span.start : span.end] == "F"
    assert result.diagnostics == ()


def test_malformed_latex_symbol_directive_warns_and_verbatim_is_ignored() -> None:
    result = LatexScanner().scan(
        _document(
            "% scieqlint-symbol: = missing\n"
            "\\begin{verbatim}\n"
            '% scieqlint-symbol: X = ignored, dim="1"\n'
            "\\end{verbatim}\n"
        ),
        Config(),
    )

    assert result.symbol_directives == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN010"]


def test_latex_symbol_directive_accepts_tex_macro_symbol() -> None:
    result = LatexScanner().scan(
        _document('% scieqlint-symbol: \\alpha = angle, dim="1"\n'),
        Config(),
    )

    assert [
        (directive.symbol, directive.description, directive.dimension)
        for directive in result.symbol_directives
    ] == [(r"\alpha", "angle", "1")]


def test_latex_symbol_directive_must_start_comment_content() -> None:
    result = LatexScanner().scan(
        _document('% note: scieqlint-symbol: X = ignored, dim="1"\n'),
        Config(),
    )

    assert result.symbol_directives == ()
    assert result.diagnostics == ()


def _document(text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath("paper.tex"), text, DocumentKind.LATEX)
