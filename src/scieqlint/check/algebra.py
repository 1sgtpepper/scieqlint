"""Small exact polynomial checker for the first SciEqLint release."""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic
from scieqlint.scan.base import MathBlock

Monomial = tuple[tuple[str, int], ...]
Polynomial = dict[Monomial, Fraction]

TOKEN_RE = re.compile(r"\\[A-Za-z]+|[A-Za-z][A-Za-z0-9_]*|\d+(?:/\d+)?|[()+\-*/^=]")


def check_algebra(block: MathBlock) -> tuple[Diagnostic, ...]:
    text = _strip_labels(block.text)
    sides = [part.strip() for part in text.split("=")]
    if len(sides) < 2:
        return ()

    diagnostics: list[Diagnostic] = []
    for left_raw, right_raw in zip(sides, sides[1:], strict=False):
        try:
            left = _Parser(left_raw).parse()
            right = _Parser(right_raw).parse()
        except UnsupportedExpressionError:
            continue

        if _symbols(left) != _symbols(right):
            continue
        residual = _sub(left, right)
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
                detail=f"left - right = {_format_poly(residual)}",
                rule="algebra",
            )
        )
    return tuple(diagnostics)


class UnsupportedExpressionError(ValueError):
    pass


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
        return _clean(expression)

    def _expr(self) -> Polynomial:
        value = self._term()
        while self._peek_value() in {"+", "-"}:
            op = self._take().value
            rhs = self._term()
            value = _add(value, rhs) if op == "+" else _sub(value, rhs)
        return value

    def _term(self) -> Polynomial:
        value = self._power()
        while True:
            peek = self._peek_value()
            if peek == "*":
                self._take()
                value = _mul(value, self._power())
            elif peek == "/":
                self._take()
                denominator = self._power()
                value = _div(value, denominator)
            elif peek is not None and (peek == "(" or _is_atom_start(peek)):
                value = _mul(value, self._power())
            else:
                return value

    def _power(self) -> Polynomial:
        value = self._atom()
        if self._peek_value() == "^":
            self._take()
            exponent_token = self._take()
            if not exponent_token.value.isdigit():
                raise UnsupportedExpressionError("non-integer exponent")
            value = _pow(value, int(exponent_token.value))
        return value

    def _atom(self) -> Polynomial:
        token = self._take()
        value = token.value
        if value == "+":
            return self._atom()
        if value == "-":
            return _neg(self._atom())
        if value == "(":
            expression = self._expr()
            if self._peek_value() != ")":
                raise UnsupportedExpressionError("missing closing parenthesis")
            self._take()
            return expression
        if value.startswith("\\"):
            raise UnsupportedExpressionError("unsupported TeX command")
        if re.fullmatch(r"\d+(?:/\d+)?", value):
            return {(): Fraction(value)}
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
            return {((value, 1),): Fraction(1)}
        raise UnsupportedExpressionError(value)

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
    return token.startswith("\\") or token.isdigit() or token[0].isalpha()


def _strip_labels(text: str) -> str:
    return re.sub(r"^[ \t]*:label:[^\n]*\n?", "", text, flags=re.MULTILINE).strip()


def _add(left: Polynomial, right: Polynomial) -> Polynomial:
    result = dict(left)
    for monomial, coefficient in right.items():
        result[monomial] = result.get(monomial, Fraction(0)) + coefficient
    return _clean(result)


def _sub(left: Polynomial, right: Polynomial) -> Polynomial:
    return _add(left, _neg(right))


def _neg(value: Polynomial) -> Polynomial:
    return {monomial: -coefficient for monomial, coefficient in value.items()}


def _mul(left: Polynomial, right: Polynomial) -> Polynomial:
    result: Polynomial = {}
    for left_monomial, left_coefficient in left.items():
        for right_monomial, right_coefficient in right.items():
            monomial = _merge_monomials(left_monomial, right_monomial)
            result[monomial] = (
                result.get(monomial, Fraction(0)) + left_coefficient * right_coefficient
            )
    return _clean(result)


def _div(left: Polynomial, right: Polynomial) -> Polynomial:
    if set(right) != {()}:
        raise UnsupportedExpressionError("division by non-constant expression")
    denominator = right[()]
    if denominator == 0:
        raise UnsupportedExpressionError("division by zero")
    return {monomial: coefficient / denominator for monomial, coefficient in left.items()}


def _pow(value: Polynomial, exponent: int) -> Polynomial:
    if exponent < 0:
        raise UnsupportedExpressionError("negative exponent")
    result: Polynomial = {(): Fraction(1)}
    for _ in range(exponent):
        result = _mul(result, value)
    return result


def _merge_monomials(left: Monomial, right: Monomial) -> Monomial:
    powers: dict[str, int] = {}
    for name, power in left + right:
        powers[name] = powers.get(name, 0) + power
    return tuple(sorted((name, power) for name, power in powers.items() if power))


def _symbols(value: Polynomial) -> set[str]:
    return {name for monomial in value for name, _power in monomial}


def _clean(value: Polynomial) -> Polynomial:
    return {monomial: coefficient for monomial, coefficient in value.items() if coefficient}


def _format_poly(value: Polynomial) -> str:
    parts: list[str] = []
    for monomial, coefficient in sorted(value.items(), key=_sort_key):
        term = _format_term(coefficient, monomial)
        if not parts:
            parts.append(term)
        elif term.startswith("-"):
            parts.append(f"- {term[1:]}")
        else:
            parts.append(f"+ {term}")
    return " ".join(parts) if parts else "0"


def _sort_key(item: tuple[Monomial, Fraction]) -> tuple[int, str]:
    monomial, _coefficient = item
    degree = sum(power for _name, power in monomial)
    return (-degree, "*".join(f"{name}^{power}" for name, power in monomial))


def _format_term(coefficient: Fraction, monomial: Monomial) -> str:
    factors: list[str] = []
    for name, power in monomial:
        factors.append(name if power == 1 else f"{name}^{power}")
    coefficient_text = _format_fraction(coefficient)
    if not factors:
        return coefficient_text
    if coefficient == 1:
        return "*".join(factors)
    if coefficient == -1:
        return "-" + "*".join(factors)
    return f"{coefficient_text}*" + "*".join(factors)


def _format_fraction(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"
