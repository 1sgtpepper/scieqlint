from __future__ import annotations

import sys
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


def test_line_separated_equations_are_checked_independently() -> None:
    diagnostics = check_algebra(_first_block("$$\nx = x\ny = y + 1\n$$\n"))

    assert [diagnostic.code for diagnostic in diagnostics] == ["ALG001"]
    assert diagnostics[0].equation == "y = y + 1"
    assert diagnostics[0].span is not None
    assert (diagnostics[0].span.line, diagnostics[0].span.col) == (3, 1)


def test_line_equation_span_preserves_indentation_after_label() -> None:
    diagnostics = check_algebra(_first_block("$$\n:label: energy\n  x = x\n  y = y + 1\n$$\n"))

    assert [diagnostic.code for diagnostic in diagnostics] == ["ALG001"]
    assert diagnostics[0].span is not None
    assert (diagnostics[0].span.line, diagnostics[0].span.col) == (4, 3)


def test_line_break_does_not_continue_an_incomplete_equation() -> None:
    diagnostics = check_algebra(_first_block("$$\nx =\nx + 1\n$$\n"))

    assert [diagnostic.code for diagnostic in diagnostics] == ["PARSE020"]
    assert diagnostics[0].equation == "x ="


def test_oversized_integer_exponent_is_controlled_unsupported_syntax() -> None:
    original_limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(sys.int_info.str_digits_check_threshold)
    try:
        oversized = "9" * 5000
        diagnostics = check_algebra(_first_block(f"$$\nx^{oversized} = x\n$$\n"))
    finally:
        sys.set_int_max_str_digits(original_limit)

    assert [diagnostic.code for diagnostic in diagnostics] == ["PARSE020"]


def test_integer_exponents_outside_the_supported_range_are_controlled() -> None:
    for exponent in ("1001", "-1001"):
        diagnostics = check_algebra(_first_block(f"$$\nx^{exponent} = x\n$$\n"))

        assert [diagnostic.code for diagnostic in diagnostics] == ["PARSE020"], exponent


def test_integer_exponent_range_includes_both_boundaries() -> None:
    for exponent in ("1000", "-1000"):
        diagnostics = check_algebra(_first_block(f"$$\nx^{exponent} = x^{exponent}\n$$\n"))

        assert diagnostics == (), exponent


def test_deeply_nested_algebra_is_controlled_unsupported_syntax() -> None:
    depth = 1000
    equation = f"{'(' * depth}x{')' * depth} = x"
    diagnostics = check_algebra(_first_block(f"$$\n{equation}\n$$\n"))

    assert [diagnostic.code for diagnostic in diagnostics] == ["PARSE020"]


def test_supported_tex_fraction_is_checked() -> None:
    diagnostics = check_algebra(_first_block("$$\n\\frac{1}{2} x = x / 2\n$$\n"))
    assert diagnostics == ()


def test_symbolic_monomial_denominator_remains_supported() -> None:
    diagnostics = check_algebra(_first_block("$$\n1/(2x) = 1/(2x)\n$$\n"))

    assert diagnostics == ()


def test_compact_rational_after_implicit_factor_is_checked() -> None:
    for equation in (
        "x\t1/2 = x / 2",
        "x 1/2 = x / 2",
        "1/2 x = x / 2",
        "x / 2 = x 1/2",
        "-1/2 x = -x / 2",
        "x 0/2 = 0",
    ):
        diagnostics = check_algebra(_first_block(f"$$\n{equation}\n$$\n"))

        assert diagnostics == (), equation


def test_compact_rational_preserves_unequal_and_symbolic_denominator_cases() -> None:
    for equation in ("1/2 x = 1/2", "x 2 = x"):
        diagnostics = check_algebra(_first_block(f"$$\n{equation}\n$$\n"))

        assert [diagnostic.code for diagnostic in diagnostics] == ["ALG001"], equation

def test_compact_rational_zero_denominator_is_controlled_unsupported_syntax() -> None:
    diagnostics = check_algebra(_first_block("$$\nx 1/0 = x\n$$\n"))

    assert [diagnostic.code for diagnostic in diagnostics] == ["PARSE020"]


def test_supported_tex_multiplication_aliases_are_checked() -> None:
    diagnostics = check_algebra(_first_block("$$\na \\cdot b = a \\times b\n$$\n"))
    assert diagnostics == ()


def test_supported_negative_powers_are_checked() -> None:
    diagnostics = check_algebra(_first_block("$$\nx^{-1} = 1 / x\n$$\n"))
    assert diagnostics == ()


def test_symbolic_sqrt_requires_a_sign_or_domain_assumption() -> None:
    diagnostics = check_algebra(_first_block("$$\n\\sqrt{x^2} = x\n$$\n"))
    assert [diagnostic.code for diagnostic in diagnostics] == ["PARSE020"]


def test_grouped_symbolic_sqrt_is_not_simplified() -> None:
    diagnostics = check_algebra(_first_block("$$\n\\sqrt{(x+1)^2} = x + 1\n$$\n"))
    assert [diagnostic.code for diagnostic in diagnostics] == ["PARSE020"]


def test_grouped_symbolic_difference_sqrt_is_not_simplified() -> None:
    diagnostics = check_algebra(_first_block("$$\n\\sqrt{(x-1)^2} = x - 1\n$$\n"))
    assert [diagnostic.code for diagnostic in diagnostics] == ["PARSE020"]


def test_symbolic_sqrt_that_normalizes_to_constant_is_not_simplified() -> None:
    for equation in ("\\sqrt{x/x} = 1", "\\sqrt{4*x/x} = 2", "\\sqrt{x^0} = 1"):
        diagnostics = check_algebra(_first_block(f"$$\n{equation}\n$$\n"))

        assert [diagnostic.code for diagnostic in diagnostics] == ["PARSE020"], equation


def test_unary_negation_binds_after_exponentiation() -> None:
    diagnostics = check_algebra(_first_block("$$\n-x^2 = x^2\n$$\n"))

    assert [diagnostic.code for diagnostic in diagnostics] == ["ALG001"]


def test_unary_signs_preserve_grouping_and_parity() -> None:
    for equation in ("+x^2 = x^2", "--x^2 = x^2", "(-x)^2 = x^2"):
        diagnostics = check_algebra(_first_block(f"$$\n{equation}\n$$\n"))

        assert diagnostics == (), equation


def test_numeric_sqrt_perfect_square_remains_supported() -> None:
    for equation in (
        "\\sqrt{0} = 0",
        "\\sqrt{1-1} = 0",
        "\\sqrt{4} = 2",
        "\\sqrt{9/4} = 3/2",
    ):
        diagnostics = check_algebra(_first_block(f"$$\n{equation}\n$$\n"))

        assert diagnostics == (), equation


def test_numeric_sqrt_non_square_is_rejected() -> None:
    for equation in ("\\sqrt{2} = 2", "\\sqrt{-4} = 2"):
        diagnostics = check_algebra(_first_block(f"$$\n{equation}\n$$\n"))

        assert [diagnostic.code for diagnostic in diagnostics] == ["PARSE020"], equation


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
