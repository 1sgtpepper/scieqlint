"""Small exact polynomial checker for the first SciEqLint release."""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from scieqlint.check.algebra_poly import (
    Polynomial,
    UnsupportedExpressionError,
    add,
    clean,
    div,
    format_poly,
    mul,
    neg,
    pow_poly,
    sqrt_poly,
    sub,
    symbols,
)
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic
from scieqlint.scan.base import MathBlock

TOKEN_RE = re.compile(r"\\[A-Za-z]+|[A-Za-z][A-Za-z0-9_]*|\d+(?:/\d+)?|[()+\-*/^=]")
TEX_MULTIPLY = {"\\cdot", "\\times"}
UNSUPPORTED_OPERATOR_TEXT_RE = re.compile(r"<=|>=|==|!=|\*\*|[<>≤≥≠≈]")
UNSUPPORTED_OPERATOR_COMMANDS = {
    "\\approx",
    "\\equiv",
    "\\ge",
    "\\geq",
    "\\gt",
    "\\le",
    "\\leq",
    "\\lt",
    "\\ne",
    "\\neq",
    "\\sim",
}


def check_algebra(block: MathBlock) -> tuple[Diagnostic, ...]:
    text = _strip_labels(block.text)
    if _contains_unsupported_operator(text):
        return (_unsupported_diagnostic(block, text, "PARSE022"),)

    sides = [part.strip() for part in text.split("=")]
    if len(sides) < 2:
        return ()

    diagnostics: list[Diagnostic] = []
    for left_raw, right_raw in zip(sides, sides[1:], strict=False):
        try:
            left = _Parser(left_raw).parse()
            right = _Parser(right_raw).parse()
        except UnsupportedExpressionError as exc:
            diagnostics.append(_unsupported_diagnostic(block, text, exc.code))
            continue

        if symbols(left) != symbols(right):
            continue
        residual = sub(left, right)
        if not residual:
            continue
        info = CATALOG["ALG001"]
        diagnostics.append(
            Diagnostic(
                code=info.code,
                severity=info.severity,
                message=info.message,
                span=block.span,
                equation=text,
                detail=f"left - right = {format_poly(residual)}",
                rule="algebra",
            )
        )
    return tuple(diagnostics)


@dataclass(frozen=True, slots=True)
class Token:
    value: str


class _Parser:
    def __init__(self, text: str) -> None:
        cleaned = text.replace("{", "(").replace("}", ")")
        tokens = TOKEN_RE.findall(cleaned)
        if "".join(tokens).replace(" ", "") != re.sub(r"\s+", "", cleaned):
            raise UnsupportedExpressionError(text)
        self.tokens = tuple(Token(token) for token in tokens)
        self.index = 0

    def parse(self) -> Polynomial:
        if not self.tokens:
            raise UnsupportedExpressionError("empty expression")
        expression = self._expr()
        if self._peek() is not None:
            raise UnsupportedExpressionError("trailing tokens")
        return clean(expression)

    def _expr(self) -> Polynomial:
        value = self._term()
        while self._peek_value() in {"+", "-"}:
            op = self._take().value
            rhs = self._term()
            value = add(value, rhs) if op == "+" else sub(value, rhs)
        return value

    def _term(self) -> Polynomial:
        value = self._power()
        while True:
            peek = self._peek_value()
            if peek == "*" or peek in TEX_MULTIPLY:
                self._take()
                value = mul(value, self._power())
            elif peek == "/":
                self._take()
                denominator = self._power()
                value = div(value, denominator)
            elif peek is not None and (peek == "(" or _is_atom_start(peek)):
                value = mul(value, self._power())
            else:
                return value

    def _power(self) -> Polynomial:
        value = self._atom()
        if self._peek_value() == "^":
            self._take()
            value = pow_poly(value, self._signed_integer())
        return value

    def _atom(self) -> Polynomial:
        token = self._take()
        value = token.value
        if value == "+":
            return self._atom()
        if value == "-":
            return neg(self._atom())
        if value == "(":
            expression = self._expr()
            if self._peek_value() != ")":
                raise UnsupportedExpressionError("missing closing parenthesis")
            self._take()
            return expression
        if value == "\\frac":
            return div(self._group(), self._group())
        if value == "\\sqrt":
            return sqrt_poly(self._group())
        if value in TEX_MULTIPLY:
            raise UnsupportedExpressionError("unexpected multiplication operator")
        if value.startswith("\\"):
            raise UnsupportedExpressionError(
                "unsupported TeX command",
                code="PARSE021" if value in UNSUPPORTED_FUNCTIONS else "PARSE020",
            )
        if re.fullmatch(r"\d+(?:/\d+)?", value):
            return {(): Fraction(value)}
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
            return {((value, 1),): Fraction(1)}
        raise UnsupportedExpressionError(value)

    def _signed_integer(self) -> int:
        sign = 1
        if self._peek_value() in {"(", "{"}:
            opening = self._take().value
            sign = self._sign()
            number = self._take()
            closing = ")" if opening == "(" else "}"
            if self._peek_value() != closing:
                raise UnsupportedExpressionError("missing exponent close")
            self._take()
        else:
            sign = self._sign()
            number = self._take()
        if not number.value.isdigit():
            raise UnsupportedExpressionError("non-integer exponent")
        return sign * int(number.value)

    def _group(self) -> Polynomial:
        if self._peek_value() != "(":
            raise UnsupportedExpressionError("missing TeX group")
        return self._atom()

    def _sign(self) -> int:
        if self._peek_value() == "+":
            self._take()
            return 1
        if self._peek_value() == "-":
            self._take()
            return -1
        return 1

    def _peek(self) -> Token | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _peek_value(self) -> str | None:
        token = self._peek()
        return token.value if token is not None else None

    def _take(self) -> Token:
        token = self._peek()
        if token is None:
            raise UnsupportedExpressionError("unexpected end of expression")
        self.index += 1
        return token


def _is_atom_start(token: str) -> bool:
    return token not in TEX_MULTIPLY and (
        token.startswith("\\") or token.isdigit() or token[0].isalpha()
    )


UNSUPPORTED_FUNCTIONS = {"\\sin", "\\cos", "\\tan", "\\log", "\\ln", "\\exp"}


def _contains_unsupported_operator(text: str) -> bool:
    if UNSUPPORTED_OPERATOR_TEXT_RE.search(text):
        return True
    return any(
        command in UNSUPPORTED_OPERATOR_COMMANDS for command in re.findall(r"\\[A-Za-z]+", text)
    )


def _strip_labels(text: str) -> str:
    stripped = re.sub(r"^[ \t]*:label:[^\n]*\n?", "", text, flags=re.MULTILINE)
    return re.sub(r"\\label\{[^{}]+}", "", stripped).strip()


def _unsupported_diagnostic(block: MathBlock, equation: str, code: str) -> Diagnostic:
    info = CATALOG[code]
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=info.message,
        span=block.span,
        equation=equation,
        rule="parser",
    )
