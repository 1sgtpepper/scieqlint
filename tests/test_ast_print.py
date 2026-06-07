from __future__ import annotations

from fractions import Fraction
from pathlib import PurePosixPath

from scieqlint.diag.model import SourceSpan
from scieqlint.parse.ast import Number, Symbol


def test_ast_number_preserves_raw_text_and_fraction() -> None:
    span = SourceSpan(PurePosixPath("paper.md"), 0, 3, 1, 1, 1, 3)
    number = Number(Fraction(1, 2), "1/2", span)
    assert number.value == Fraction(1, 2)
    assert number.raw == "1/2"
    assert number.span is span


def test_ast_symbol_preserves_raw_text() -> None:
    span = SourceSpan(PurePosixPath("paper.md"), 0, 1, 1, 1, 1, 1)
    symbol = Symbol("x", "x", span)
    assert symbol.name == "x"
    assert symbol.raw == "x"
