"""Small exact polynomial checker for the first SciEqLint release."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from fractions import Fraction
from math import isqrt

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.scan.base import MathBlock

Monomial = tuple[tuple[str, int], ...]
Polynomial = dict[Monomial, Fraction]

TOKEN_RE = re.compile(r"\\[A-Za-z]+|[A-Za-z][A-Za-z0-9_]*|\d+(?:/\d+)?|[()+\-*/^=]")
TEX_MULTIPLY = {"\\cdot", "\\times"}
_MAX_ABS_EXPONENT = 1_000


@dataclass(frozen=True, slots=True)
class _EquationLine:
    text: str
    start: int
    end: int


def check_algebra(block: MathBlock) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for equation in _equation_lines(block.text):
        sides = [part.strip() for part in equation.text.split("=")]
        span = _equation_span(block, equation)

        for left_raw, right_raw in zip(sides, sides[1:], strict=False):
            try:
                left = _Parser(left_raw).parse()
                right = _Parser(right_raw).parse()
            except UnsupportedExpressionError as exc:
                diagnostics.append(_unsupported_diagnostic(span, equation.text, exc.code))
                continue
            except RecursionError:
                # Deeply nested groups are unsupported, not checker failures.
                diagnostics.append(_unsupported_diagnostic(span, equation.text, "PARSE020"))
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
                    span=span,
                    equation=equation.text,
                    detail=f"left - right = {_format_poly(residual)}",
                    rule="algebra",
                )
            )
    return tuple(diagnostics)


def _equation_lines(text: str) -> tuple[_EquationLine, ...]:
    masked = _mask_labels(text)
    equations: list[_EquationLine] = []
    offset = 0
    for line in masked.splitlines(keepends=True):
        line_end = offset + len(line)
        content_end = line_end - (1 if line.endswith("\n") else 0)
        content = masked[offset:content_end]
        start = offset + len(content) - len(content.lstrip())
        end = offset + len(content.rstrip())
        if "=" in content[start - offset : end - offset]:
            equations.append(_EquationLine(masked[start:end], start, end))
        offset = line_end
    return tuple(equations)


class UnsupportedExpressionError(ValueError):
    def __init__(self, message: str, *, code: str = "PARSE020") -> None:
        super().__init__(message)
        self.code = code


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
            if peek == "*" or peek in TEX_MULTIPLY:
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
        sign = 1
        while self._peek_value() in {"+", "-"}:
            if self._take().value == "-":
                sign = -sign
        value = self._atom()
        if self._peek_value() == "^":
            self._take()
            value = _pow(value, self._signed_integer())
        return _neg(value) if sign == -1 else value

    def _atom(self) -> Polynomial:
        token = self._take()
        value = token.value
        if value == "(":
            expression = self._expr()
            if self._peek_value() != ")":
                raise UnsupportedExpressionError("missing closing parenthesis")
            self._take()
            return expression
        if value == "\\frac":
            return _div(self._group(), self._group())
        if value == "\\sqrt":
            operand_start = self.index
            operand = self._group()
            root = _sqrt(operand)
            # Preserve the original root operand's symbol information before
            # normalization can erase it through cancellation or exponent zero.
            if any(
                re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", token.value)
                for token in self.tokens[operand_start : self.index]
            ):
                raise UnsupportedExpressionError("sqrt of symbolic expression")
            return root
        if value in TEX_MULTIPLY:
            raise UnsupportedExpressionError("unexpected multiplication operator")
        if value.startswith("\\"):
            raise UnsupportedExpressionError(
                "unsupported TeX command",
                code="PARSE021" if value in UNSUPPORTED_FUNCTIONS else "PARSE020",
            )
        if re.fullmatch(r"\d+(?:/\d+)?", value):
            try:
                number = Fraction(value)
            except ZeroDivisionError as exc:
                raise UnsupportedExpressionError("division by zero") from exc
            return {(): number}
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
        try:
            exponent = int(number.value)
        except ValueError as exc:
            raise UnsupportedExpressionError("invalid integer exponent") from exc
        exponent *= sign
        if abs(exponent) > _MAX_ABS_EXPONENT:
            raise UnsupportedExpressionError("integer exponent outside supported range")
        return exponent

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
        token.startswith("\\")
        or re.fullmatch(r"\d+(?:/\d+)?", token) is not None
        or token[0].isalpha()
    )


UNSUPPORTED_FUNCTIONS = {"\\sin", "\\cos", "\\tan", "\\log", "\\ln", "\\exp"}


def _mask_labels(text: str) -> str:
    masked = re.sub(
        r"^[ \t]*:label:[^\n]*(?:\n|$)",
        _spaces_for_match,
        text,
        flags=re.MULTILINE,
    )
    return re.sub(r"\\label\{[^{}]+}", _spaces_for_match, masked)


def _spaces_for_match(match: re.Match[str]) -> str:
    return "".join("\n" if char == "\n" else " " for char in match.group(0))


def _equation_span(block: MathBlock, equation: _EquationLine) -> SourceSpan:
    if block.span.end - block.span.start != len(block.text):
        return block.span

    start_line, start_col = _relative_position(block, equation.start)
    end_line, end_col = _relative_position(block, max(equation.start, equation.end - 1))
    return replace(
        block.span,
        start=block.span.start + equation.start,
        end=block.span.start + equation.end,
        line=start_line,
        col=start_col,
        end_line=end_line,
        end_col=end_col,
    )


def _relative_position(block: MathBlock, offset: int) -> tuple[int, int]:
    prefix = block.text[:offset]
    if "\n" in prefix:
        return block.span.line + prefix.count("\n"), len(prefix.rsplit("\n", 1)[-1]) + 1
    return block.span.line, block.span.col + len(prefix)


def _unsupported_diagnostic(span: SourceSpan, equation: str, code: str) -> Diagnostic:
    info = CATALOG[code]
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=info.message,
        span=span,
        equation=equation,
        rule="parser",
    )


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
    if len(right) != 1:
        raise UnsupportedExpressionError("division by non-constant expression")
    monomial, denominator = next(iter(right.items()))
    if denominator == 0:
        raise UnsupportedExpressionError("division by zero")
    divisor = tuple((name, -power) for name, power in monomial)
    return {
        _merge_monomials(left_monomial, divisor): coefficient / denominator
        for left_monomial, coefficient in left.items()
    }


def _pow(value: Polynomial, exponent: int) -> Polynomial:
    result: Polynomial = {(): Fraction(1)}
    base = value if exponent >= 0 else _div({(): Fraction(1)}, value)
    for _ in range(abs(exponent)):
        result = _mul(result, base)
    return result


def _sqrt(value: Polynomial) -> Polynomial:
    if not value:
        return {(): Fraction(0)}
    if len(value) != 1:
        raise UnsupportedExpressionError("sqrt of non-constant expression")
    monomial, coefficient = next(iter(value.items()))
    if monomial:
        raise UnsupportedExpressionError("sqrt of non-constant expression")
    root = _integer_sqrt(coefficient)
    if root is None:
        raise UnsupportedExpressionError("sqrt of non-square constant")
    return {(): root}


def _integer_sqrt(value: Fraction) -> Fraction | None:
    if value < 0:
        return None
    numerator = isqrt(value.numerator)
    denominator = isqrt(value.denominator)
    if numerator * numerator == value.numerator and denominator * denominator == value.denominator:
        return Fraction(numerator, denominator)
    return None


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
