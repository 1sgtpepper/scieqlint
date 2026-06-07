from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.check.algebra import check_algebra
from scieqlint.config.model import Config
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.markdown import MarkdownScanner


def _first_block(text: str):
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)
    return MarkdownScanner().scan(document, Config()).blocks[0]


def test_false_polynomial_identity_reports_residual() -> None:
    diagnostics = check_algebra(_first_block("$$\n(a+b)^2 = a^2 + b^2\n$$\n"))
    assert [diagnostic.code for diagnostic in diagnostics] == ["ALG001"]
    assert diagnostics[0].detail == "left - right = 2*a*b"


def test_true_polynomial_identity_is_quiet() -> None:
    diagnostics = check_algebra(_first_block("$$\n(a+b)^2 = a^2 + 2*a*b + b^2\n$$\n"))
    assert diagnostics == ()


def test_supported_tex_fraction_is_checked() -> None:
    diagnostics = check_algebra(_first_block("$$\n\\frac{1}{2} x = x / 2\n$$\n"))
    assert diagnostics == ()


def test_supported_tex_multiplication_aliases_are_checked() -> None:
    diagnostics = check_algebra(_first_block("$$\na \\cdot b = a \\times b\n$$\n"))
    assert diagnostics == ()


def test_supported_negative_powers_are_checked() -> None:
    diagnostics = check_algebra(_first_block("$$\nx^{-1} = 1 / x\n$$\n"))
    assert diagnostics == ()


def test_supported_sqrt_perfect_square_is_checked() -> None:
    diagnostics = check_algebra(_first_block("$$\n\\sqrt{x^2} = x\n$$\n"))
    assert diagnostics == ()


def test_supported_sqrt_grouped_square_expression_is_checked() -> None:
    diagnostics = check_algebra(_first_block("$$\n\\sqrt{(x+1)^2} = x + 1\n$$\n"))
    assert diagnostics == ()


def test_supported_sqrt_grouped_difference_square_is_checked() -> None:
    diagnostics = check_algebra(_first_block("$$\n\\sqrt{(x-1)^2} = x - 1\n$$\n"))
    assert diagnostics == ()


def test_tex_fraction_requires_grouped_operands() -> None:
    diagnostics = check_algebra(_first_block("$$\n\\frac 1 2 = 1/2\n$$\n"))
    assert [diagnostic.code for diagnostic in diagnostics] == ["PARSE020"]


def test_tex_sqrt_requires_grouped_operand() -> None:
    diagnostics = check_algebra(_first_block("$$\n\\sqrt 4 = 2\n$$\n"))
    assert [diagnostic.code for diagnostic in diagnostics] == ["PARSE020"]


def test_assignment_with_different_symbols_is_not_treated_as_identity() -> None:
    diagnostics = check_algebra(_first_block("$$\nE = m c^2\n$$\n"))
    assert diagnostics == ()


def test_unsupported_trig_reports_parse_unknown() -> None:
    diagnostics = check_algebra(_first_block("$$\n\\sin(x) = x\n$$\n"))
    assert [diagnostic.code for diagnostic in diagnostics] == ["PARSE021"]
    assert diagnostics[0].rule == "parser"
