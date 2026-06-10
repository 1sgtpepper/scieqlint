"""Dimension-expression parser used by configured dimension checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import cast

from scieqlint.config.model import Config, DimVector
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic
from scieqlint.scan.base import MathBlock

TOKEN_PATTERN = r"\\[A-Za-z]+|[A-Za-z][A-Za-z0-9_]*|\d+(?:/\d+)?|[()+\-*/^=]"
TEX_MULTIPLY = {"\\cdot", "\\times"}

_DIMENSIONLESS = DimVector((0, 0, 0, 0, 0, 0, 0))


@dataclass(frozen=True, slots=True)
class DimensionResult:
    value: DimVector | None
    diagnostics: tuple[Diagnostic, ...] = ()


def parse_dimension_expression(
    text: str,
    block: MathBlock,
    equation: str,
    dimensions: dict[str, DimVector],
    aliases: dict[str, str],
    config: Config,
) -> DimensionResult:
    return _Parser(text, block, equation, dimensions, aliases, config).parse()


@dataclass(slots=True)
class _Parser:
    text: str
    block: MathBlock
    equation: str
    dimensions: dict[str, DimVector]
    aliases: dict[str, str]
    config: Config
    tokens: tuple[str, ...] = field(init=False)
    index: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        cleaned = self.text.replace("{", "(").replace("}", ")")
        tokens = _token_re(tuple(self.aliases)).findall(cleaned)
        if "".join(tokens).replace(" ", "") != re.sub(r"\s+", "", cleaned):
            tokens = ()
        self.tokens = tuple(tokens)

    def parse(self) -> DimensionResult:
        if not self.tokens:
            return self._skipped()
        result = self._expr()
        if self._peek() is not None:
            return self._combine(result, self._skipped())
        return result

    def _expr(self) -> DimensionResult:
        value = self._term()
        while self._peek() in {"+", "-"}:
            self._take()
            value = self._add_sub(value, self._term())
        return value

    def _term(self) -> DimensionResult:
        value = self._power()
        while True:
            peek = self._peek()
            if peek == "*" or peek in TEX_MULTIPLY:
                self._take()
                value = self._mul(value, self._power(), 1)
            elif peek == "/":
                self._take()
                value = self._mul(value, self._power(), -1)
            elif peek is not None and (peek == "(" or _is_atom_start(peek)):
                value = self._mul(value, self._power(), 1)
            else:
                return value

    def _power(self) -> DimensionResult:
        value = self._atom()
        if self._peek() != "^":
            return value
        self._take()
        exponent = self._signed_integer()
        if exponent is None or value.value is None:
            return self._combine(value, self._skipped())
        return self._with_diagnostics(_scale(value.value, exponent), value.diagnostics)

    def _atom(self) -> DimensionResult:
        token = self._take()
        if token is None:
            return self._skipped()
        if token in {"+", "-"}:
            return self._atom()
        if token == "(":
            expression = self._expr()
            if self._peek() != ")":
                return self._combine(expression, self._skipped())
            self._take()
            return expression
        if token == "\\frac":
            return self._mul(self._group(), self._group(), -1)
        if token == "\\sqrt":
            return self._sqrt(self._group())
        if token in TEX_MULTIPLY:
            return self._skipped()
        if token.startswith("\\"):
            if token in self.aliases:
                return self._symbol(token)
            return self._skipped()
        if re.fullmatch(r"\d+(?:/\d+)?", token):
            return DimensionResult(_DIMENSIONLESS)
        if _is_symbol_token(token) or token in self.aliases:
            return self._symbol(token)
        return self._skipped()

    def _group(self) -> DimensionResult:
        if self._peek() != "(":
            return self._skipped()
        return self._atom()

    def _sqrt(self, value: DimensionResult) -> DimensionResult:
        if value.value is None:
            return value
        if any(exponent % 2 for exponent in value.value.exponents):
            return self._combine(value, self._skipped())
        return self._with_diagnostics(_scale(value.value, 1, divisor=2), value.diagnostics)

    def _symbol(self, name: str) -> DimensionResult:
        canonical = self.aliases.get(name, name)
        dimension = self.dimensions.get(canonical)
        if dimension is not None:
            return DimensionResult(dimension)
        if self.config.checks.dimension.unknown_variables == "ignore":
            return DimensionResult(None)
        return DimensionResult(None, (_diagnostic(self.block, self.equation, "DIM010", name),))

    def _add_sub(self, left: DimensionResult, right: DimensionResult) -> DimensionResult:
        diagnostics = (*left.diagnostics, *right.diagnostics)
        if left.value is None or right.value is None:
            return DimensionResult(None, diagnostics)
        if left.value != right.value:
            return DimensionResult(
                None,
                (
                    *diagnostics,
                    _diagnostic(
                        self.block,
                        self.equation,
                        "DIM002",
                        mismatch_detail(left.value, right.value),
                    ),
                ),
            )
        return DimensionResult(left.value, diagnostics)

    def _mul(
        self,
        left: DimensionResult,
        right: DimensionResult,
        right_sign: int,
    ) -> DimensionResult:
        diagnostics = (*left.diagnostics, *right.diagnostics)
        if left.value is None or right.value is None:
            return DimensionResult(None, diagnostics)
        return DimensionResult(_combine_vectors(left.value, right.value, right_sign), diagnostics)

    def _combine(self, left: DimensionResult, right: DimensionResult) -> DimensionResult:
        return DimensionResult(None, (*left.diagnostics, *right.diagnostics))

    def _skipped(self) -> DimensionResult:
        return DimensionResult(None, (_diagnostic(self.block, self.equation, "DIM020"),))

    def _with_diagnostics(
        self,
        value: DimVector,
        diagnostics: tuple[Diagnostic, ...],
    ) -> DimensionResult:
        return DimensionResult(value, diagnostics)

    def _signed_integer(self) -> int | None:
        sign = 1
        if self._peek() == "(":
            self._take()
            sign = self._sign()
            number = self._take()
            if self._peek() != ")":
                return None
            self._take()
        else:
            sign = self._sign()
            number = self._take()
        if number is None or not number.isdigit():
            return None
        return sign * int(number)

    def _sign(self) -> int:
        if self._peek() == "+":
            self._take()
            return 1
        if self._peek() == "-":
            self._take()
            return -1
        return 1

    def _peek(self) -> str | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _take(self) -> str | None:
        token = self._peek()
        if token is not None:
            self.index += 1
        return token


def _is_atom_start(token: str) -> bool:
    return token not in TEX_MULTIPLY and (
        token.startswith("\\") or token.isdigit() or token[0].isalpha()
    )


def _is_symbol_token(token: str) -> bool:
    return re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", token) is not None


def _token_re(aliases: tuple[str, ...]) -> re.Pattern[str]:
    alias_pattern = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    if not alias_pattern:
        return re.compile(TOKEN_PATTERN)
    return re.compile(f"{alias_pattern}|{TOKEN_PATTERN}")


def _combine_vectors(left: DimVector, right: DimVector, right_sign: int) -> DimVector:
    return _dim_vector(
        [
            left_exponent + right_sign * right_exponent
            for left_exponent, right_exponent in zip(left.exponents, right.exponents, strict=True)
        ]
    )


def _scale(value: DimVector, multiplier: int, *, divisor: int = 1) -> DimVector:
    return _dim_vector([exponent * multiplier // divisor for exponent in value.exponents])


def _dim_vector(exponents: list[int]) -> DimVector:
    return DimVector(cast(tuple[int, int, int, int, int, int, int], tuple(exponents)))


def mismatch_detail(left: DimVector, right: DimVector) -> str:
    return f"left dimension {_format_dimension(left)}; right dimension {_format_dimension(right)}"


def _format_dimension(value: DimVector) -> str:
    names = ("M", "L", "T", "I", "Theta", "N", "J")
    parts = [
        name if exponent == 1 else f"{name}^{exponent}"
        for name, exponent in zip(names, value.exponents, strict=True)
        if exponent
    ]
    return "1" if not parts else " ".join(parts)


def _diagnostic(
    block: MathBlock,
    equation: str,
    code: str,
    detail: str | None = None,
) -> Diagnostic:
    info = CATALOG[code]
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=info.message,
        span=block.span,
        equation=equation,
        detail=detail,
        rule="dimensions",
    )
