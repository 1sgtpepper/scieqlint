from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from scieqlint import __version__
from scieqlint.api import check_documents
from scieqlint.config.model import ChecksConfig, Config, SymbolsConfig
from scieqlint.diag.model import Diagnostic, Severity, SourceSpan
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan import latex as latex_module
from scieqlint.scan.base import (
    LabelSource,
    MathContainer,
    ReferenceSource,
    SymbolDirectiveSource,
)
from scieqlint.scan.latex import LatexScanner


class _CharacterWorkText(str):
    def __new__(cls, value: str):
        instance = super().__new__(cls, value)
        instance.character_work = 0
        return instance

    def __getitem__(self, key):
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            self.character_work += len(range(start, stop, step))
        else:
            self.character_work += 1
        return super().__getitem__(key)


def test_align_row_scanning_bounds_backslash_character_work() -> None:
    source = _CharacterWorkText("\\" * 2_048)

    rows = tuple(latex_module._align_rows(source, 0, len(source), ()))

    assert len(rows) == 1_025
    assert source.character_work <= 10 * len(source)


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


@pytest.mark.public_regression
def test_latex_normalization_preserves_symbol_source_spans() -> None:
    source = "\\begin{align}\n  % removed comment\n  x &= y\n\\end{align}\n"
    document = _document(source)

    result = check_documents(
        [document],
        config=Config(checks=ChecksConfig(symbols=SymbolsConfig(enabled=True))),
    )

    x_start = source.index("x &=")
    y_start = source.index("y", x_start)
    assert result.files_checked == 1
    assert result.math_blocks_checked == 1
    assert result.config_path is None
    assert result.show_suppressed is False
    assert result.exit_code() == 0
    assert result.diagnostics == (
        Diagnostic(
            code="SYM001",
            severity=Severity.WARNING,
            message="undefined symbol: x",
            span=SourceSpan(
                path=PurePosixPath("paper.tex"),
                start=x_start,
                end=x_start + 1,
                line=3,
                col=3,
                end_line=3,
                end_col=3,
            ),
            detail="x",
            rule="symbols",
        ),
        Diagnostic(
            code="SYM001",
            severity=Severity.WARNING,
            message="undefined symbol: y",
            span=SourceSpan(
                path=PurePosixPath("paper.tex"),
                start=y_start,
                end=y_start + 1,
                line=3,
                col=8,
                end_line=3,
                end_col=8,
            ),
            detail="y",
            rule="symbols",
        ),
    )
    assert [
        document.text[diagnostic.span.start : diagnostic.span.end]
        for diagnostic in result.diagnostics
        if diagnostic.span is not None
    ] == ["x", "y"]


def test_latex_symbol_source_span_control() -> None:
    source = "\\begin{equation}\nq = r\n\\end{equation}\n"
    document = _document(source)

    result = check_documents(
        [document],
        config=Config(checks=ChecksConfig(symbols=SymbolsConfig(enabled=True))),
    )

    assert [
        (
            diagnostic.detail,
            diagnostic.span.line,
            diagnostic.span.col,
            document.text[diagnostic.span.start : diagnostic.span.end],
        )
        for diagnostic in result.diagnostics
        if diagnostic.span is not None
    ] == [("q", 2, 1, "q"), ("r", 2, 5, "r")]


@pytest.mark.parametrize(
    ("source", "expected_text", "expected_aligned_text", "expected_container"),
    [
        pytest.param(
            "\\begin{equation}\n  % note\n  E = m c^2 % tail\n\\end{equation}\n",
            "E = m c^2",
            " " * len("% note") + "\n  E = m c^2 " + " " * len("% tail"),
            MathContainer.LATEX_EQUATION,
            id="equation",
        ),
        pytest.param(
            "\\begin{equation*}\na = b\n\\end{equation*}\n",
            "a = b",
            "a = b",
            MathContainer.LATEX_EQUATION,
            id="equation-star",
        ),
        pytest.param(
            "\\[\nc = d\n\\]\n",
            "c = d",
            "c = d",
            MathContainer.LATEX_DISPLAY,
            id="display",
        ),
        pytest.param(
            "$$\ne = f\n$$\n",
            "e = f",
            "e = f",
            MathContainer.LATEX_DISPLAY,
            id="dollars",
        ),
        pytest.param(
            "\\begin{align}\nA &= B\n\\end{align}\n",
            "A = B",
            "A  = B",
            MathContainer.LATEX_ALIGN,
            id="align",
        ),
        pytest.param(
            "\\begin{align*}\nC &= D\n\\end{align*}\n",
            "C = D",
            "C  = D",
            MathContainer.LATEX_ALIGN,
            id="align-star",
        ),
    ],
)
def test_latex_blocks_keep_normalized_and_source_aligned_text(
    source: str,
    expected_text: str,
    expected_aligned_text: str,
    expected_container: MathContainer,
) -> None:
    document = _document(source)

    result = LatexScanner().scan(document, Config())

    assert len(result.blocks) == 1
    block = result.blocks[0]
    raw_text = document.text[block.span.start : block.span.end]
    assert (block.text, block.source_aligned_text, block.container) == (
        expected_text,
        expected_aligned_text,
        expected_container,
    )
    assert len(block.source_aligned_text) == len(raw_text)
    assert block.source_aligned_text.count("\n") == raw_text.count("\n")


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            "\\begin{equation}\n% comment\n\\end{equation}\n",
            id="equation",
        ),
        pytest.param(
            "\\begin{align}\n% comment\n\\end{align}\n",
            id="align",
        ),
    ],
)
def test_latex_comment_only_math_is_not_a_block(source: str) -> None:
    result = LatexScanner().scan(_document(source), Config())

    assert result.blocks == ()


def test_latex_source_alignment_preserves_lexical_boundaries() -> None:
    source = (
        "\\begin{align*}\n"
        r"  x&y &= z \% literal % hidden \\"
        "\n"
        r"  u \& v &= w \label{eq:w} \\"
        "\n"
        "  p\u0301 &= q\n"
        "\\end{align*}\n"
    )
    document = _document(source)

    scan = LatexScanner().scan(document, Config())

    assert len(scan.blocks) == 3
    assert [block.source_aligned_text for block in scan.blocks] == [
        r"x y  = z \% literal " + " " * len("% hidden"),
        r"u \& v  = w \label{eq:w}",
        "p\u0301  = q",
    ]
    for block in scan.blocks:
        assert len(block.source_aligned_text) == block.span.end - block.span.start

    result = check_documents(
        [document],
        config=Config(checks=ChecksConfig(symbols=SymbolsConfig(enabled=True))),
    )
    symbol_diagnostics = tuple(
        diagnostic for diagnostic in result.diagnostics if diagnostic.code == "SYM001"
    )
    assert [diagnostic.detail for diagnostic in symbol_diagnostics] == [
        "x",
        "y",
        "z",
        "literal",
        "u",
        "v",
        "w",
        "p",
        "q",
    ]
    for diagnostic in symbol_diagnostics:
        assert diagnostic.span is not None
        assert document.text[diagnostic.span.start : diagnostic.span.end] == diagnostic.detail


def test_latex_alignment_marker_after_row_break_uses_new_row_coordinates() -> None:
    result = LatexScanner().scan(
        _document("\\begin{align}\na \\\\&= b\n\\end{align}\n"),
        Config(),
    )

    assert [(block.text, block.source_aligned_text) for block in result.blocks] == [
        ("a", "a"),
        ("= b", " = b"),
    ]


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


def test_escaped_dollar_candidate_does_not_skip_overlapping_opening() -> None:
    result = LatexScanner().scan(_document(r"\$$$x=x$$" + "\n"), Config())

    assert [block.text for block in result.blocks] == ["x=x"]
    assert result.diagnostics == ()


def test_escaped_dollar_candidate_does_not_skip_overlapping_closing() -> None:
    result = LatexScanner().scan(_document(r"$$x=x\$$$" + "\n"), Config())

    assert [block.text for block in result.blocks] == [r"x=x\$"]
    assert result.diagnostics == ()


def test_comment_delimiter_is_ignored_before_the_live_dollar_close() -> None:
    result = LatexScanner().scan(
        _document("$$\nx = x % $$\ny = y\n$$\n"),
        Config(),
    )

    assert [block.text for block in result.blocks] == ["x = x\ny = y"]
    assert result.diagnostics == ()


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


@pytest.mark.public_regression
def test_public_commented_verbatim_markers_do_not_hide_live_equations() -> None:
    source = (
        "% \\begin{verbatim}\n"
        "\\begin{equation}\n"
        "x = x + 1\n"
        "\\end{equation}\n"
        "% \\end{verbatim}\n"
        "\\% \\begin{equation}y = y\\end{equation}\n"
    )
    result = check_documents(
        [_document(source)],
        config=Config(),
    )

    equation_start = source.index("x = x + 1")
    equation_end = equation_start + len("x = x + 1")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 2
    assert result.config_path is None
    assert result.version == __version__
    assert result.diagnostics == (
        Diagnostic(
            code="ALG001",
            severity=Severity.ERROR,
            message="algebraic identity does not hold",
            span=SourceSpan(
                path=PurePosixPath("paper.tex"),
                start=equation_start,
                end=equation_end,
                line=3,
                col=1,
                end_line=3,
                end_col=len("x = x + 1"),
            ),
            equation="x = x + 1",
            detail="left - right = -1",
            rule="algebra",
        ),
    )


@pytest.mark.public_regression
def test_public_starred_verbatim_is_opaque() -> None:
    result = check_documents(
        [
            _document(
                "\\begin{verbatim*}\n"
                "\\begin{equation}\n"
                "x = x + 1\n"
                "\\end{equation}\n"
                "See \\ref{ghost}.\n"
                "\\end{verbatim*}\n"
                "\\begin{equation}\n"
                "y = y\n"
                "\\end{equation}\n"
            )
        ],
        config=Config(),
    )

    assert result.files_checked == 1
    assert result.math_blocks_checked == 1
    assert result.diagnostics == ()
    assert result.exit_code() == 0


def test_verbatim_closer_requires_the_matching_starred_form() -> None:
    result = LatexScanner().scan(
        _document(
            "\\begin{verbatim*}\n"
            "\\end{verbatim}\n"
            "\\begin{equation}\n"
            "x = x + 1\n"
            "\\end{equation}\n"
            "\\end{verbatim*}\n"
            "\\begin{equation}\n"
            "y = y\n"
            "\\end{equation}\n"
        ),
        Config(),
    )

    assert [block.text for block in result.blocks] == ["y = y"]


def test_mismatched_verbatim_closer_at_eof_keeps_region_opaque() -> None:
    result = LatexScanner().scan(
        _document(
            "\\begin{equation}y = y\\end{equation}\n"
            "\\begin{verbatim}\n"
            "\\begin{equation}x = x + 1\\end{equation}\n"
            "\\end{verbatim*}"
        ),
        Config(),
    )

    assert [block.text for block in result.blocks] == ["y = y"]
    assert result.diagnostics == ()


def test_verbatim_closer_inside_percent_content_is_literal_delimiter() -> None:
    result = LatexScanner().scan(
        _document(
            "\\begin{verbatim}\n% \\end{verbatim}\n\\begin{equation}\nx = x + 1\n\\end{equation}\n"
        ),
        Config(),
    )

    assert [block.text for block in result.blocks] == ["x = x + 1"]


def test_same_line_verbatim_close_then_new_verbatim_open_is_compositional() -> None:
    result = LatexScanner().scan(
        _document(
            "\\begin{equation}y = y\\end{equation}\n"
            "\\begin{verbatim}%\\end{verbatim} \\begin{verbatim}\n"
            "\\begin{equation}\n"
            "x = x + 1\n"
            "\\end{equation}\n"
            "\\end{verbatim}\n"
        ),
        Config(),
    )

    assert [block.text for block in result.blocks] == ["y = y"]


def test_same_line_verbatim_close_then_comment_hides_following_equation() -> None:
    result = LatexScanner().scan(
        _document(
            "\\begin{equation}y = y\\end{equation}\n"
            "\\begin{verbatim}%\\end{verbatim} % \\begin{equation}x = x + 1\\end{equation}\n"
        ),
        Config(),
    )

    assert [block.text for block in result.blocks] == ["y = y"]


def test_same_line_verbatim_close_exposes_following_symbol_comment() -> None:
    result = LatexScanner().scan(
        _document('\\begin{verbatim}%\\end{verbatim} % scieqlint-symbol: X = active, dim="1"\n'),
        Config(),
    )

    assert [directive.symbol for directive in result.symbol_directives] == ["X"]


def test_unclosed_verbatim_protects_the_remaining_source() -> None:
    result = LatexScanner().scan(
        _document(
            "\\begin{equation}y = y\\end{equation}\n"
            "\\begin{verbatim}\n"
            "\\begin{equation}\nx = x + 1\n\\end{equation}\n"
            "See \\ref{ghost}.\n"
        ),
        Config(),
    )

    assert [block.text for block in result.blocks] == ["y = y"]
    assert result.references == ()
    assert result.diagnostics == ()


def test_verbatim_closer_can_occur_mid_line() -> None:
    result = LatexScanner().scan(
        _document(
            "\\begin{verbatim}\n"
            "prefix\\end{verbatim}\n"
            "\\begin{equation}\n"
            "x = x + 1\n"
            "\\end{equation}\n"
        ),
        Config(),
    )

    assert [block.text for block in result.blocks] == ["x = x + 1"]


@pytest.mark.public_regression
def test_public_escaped_tex_controls_require_active_boundaries() -> None:
    result = check_documents(
        [
            _document(
                r"Text \\begin{equation}"
                "\n"
                r"See \\ref{ghost}."
                "\n"
                r"\\\begin{equation}"
                "\n"
                "y = y\n"
                "\\label{odd}\n"
                r"\\\end{equation}"
                "\n"
                r"See \\\ref{odd}."
                "\n"
            )
        ],
        config=Config(),
    )

    assert result.math_blocks_checked == 1
    assert result.diagnostics == ()


def test_escaped_environment_closer_does_not_end_live_equation() -> None:
    result = LatexScanner().scan(
        _document(
            r"\begin{equation}" + "\n"
            "x = x + 1\n"
            r"\\end{equation}" + "\n"
            r"\end{equation}" + "\n"
        ),
        Config(),
    )

    assert len(result.blocks) == 1
    assert result.blocks[0].text == "x = x + 1\n\\\\end{equation}"


@pytest.mark.public_regression
def test_public_escaped_verbatim_markers_leave_live_equations_active() -> None:
    source = (
        r"\\begin{verbatim}"
        "\n"
        r"\begin{equation}"
        "\n"
        "x = x + 1\n"
        r"\end{equation}"
        "\n"
        r"\\end{verbatim}"
        "\n"
    )
    result = check_documents(
        [_document(source)],
        config=Config(),
    )

    equation_start = source.index("x = x + 1")
    equation_end = equation_start + len("x = x + 1")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 1
    assert result.config_path is None
    assert result.version == __version__
    assert result.diagnostics == (
        Diagnostic(
            code="ALG001",
            severity=Severity.ERROR,
            message="algebraic identity does not hold",
            span=SourceSpan(
                path=PurePosixPath("paper.tex"),
                start=equation_start,
                end=equation_end,
                line=3,
                col=1,
                end_line=3,
                end_col=len("x = x + 1"),
            ),
            equation="x = x + 1",
            detail="left - right = -1",
            rule="algebra",
        ),
    )


def test_verbatim_closer_ignores_backslash_parity() -> None:
    for slash_count in (1, 2, 3, 4):
        closer = "\\" * slash_count + "end{verbatim}"
        result = LatexScanner().scan(
            _document(
                "\\begin{verbatim}\n"
                "\\begin{equation}\n"
                "x = x + 1\n"
                "\\end{equation}\n"
                f"{closer}\n"
                "\\begin{equation}\n"
                "y = y + 1\n"
                "\\end{equation}\n"
            ),
            Config(),
        )

        assert [block.text for block in result.blocks] == ["y = y + 1"]


def test_comment_row_break_does_not_reactivate_comment_text() -> None:
    result = check_documents(
        [
            _document(
                "\\begin{align}\nx &= x % \\\\ ghost = ghost + 1\n\\\\\ny &= y\n\\end{align}\n"
            )
        ],
        config=Config(),
    )

    assert result.math_blocks_checked == 2
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


@pytest.mark.public_regression
def test_public_escaped_latex_labels_are_not_equation_labels() -> None:
    source = (
        "\\begin{equation}\n"
        "x = x\n"
        "\\label{real}\n"
        r"\\label{escaped}"
        "\n"
        "\\end{equation}\n"
        "See \\ref{real} and \\ref{escaped}.\n"
    )
    result = check_documents([_document(source)], config=Config())

    target_start = source.rindex("escaped")
    target_end = target_start + len("escaped")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 1
    assert result.config_path is None
    assert result.version == __version__
    assert result.diagnostics == (
        Diagnostic(
            code="REF002",
            severity=Severity.WARNING,
            message="equation reference target not found: escaped",
            span=SourceSpan(
                path=PurePosixPath("paper.tex"),
                start=target_start,
                end=target_end,
                line=6,
                col=25,
                end_line=6,
                end_col=31,
            ),
            detail=r"reference text: \ref{escaped}",
            rule="references",
        ),
    )


def test_carriage_return_ends_a_latex_comment() -> None:
    result = LatexScanner().scan(
        _document("% \\begin{verbatim}\r\\begin{equation}\ry = y\r\\end{equation}\r"),
        Config(),
    )

    assert [block.text for block in result.blocks] == ["y = y"]


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


def test_latex_verbatim_transition_fixture_keeps_only_live_equation() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("tests/fixtures/good/verbatim_transitions.tex"),
        Path("tests/fixtures/good/verbatim_transitions.tex").read_text(encoding="utf-8"),
        DocumentKind.LATEX,
    )

    result = LatexScanner().scan(document, Config())

    assert [block.text for block in result.blocks] == ["E = m c^2"]
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


@pytest.mark.parametrize("ending", ["\n", ""], ids=["newline", "eof"])
def test_latex_symbol_directive_accepts_tex_macro_symbol(ending: str) -> None:
    result = LatexScanner().scan(
        _document(f'% scieqlint-symbol: \\alpha = angle, dim="1"{ending}'),
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
