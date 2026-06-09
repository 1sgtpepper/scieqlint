"""Configured physical-dimension checks."""

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


def check_dimensions(block: MathBlock, config: Config) -> tuple[Diagnostic, ...]:
    if not config.checks.dimension.is_active(has_vars=bool(config.vars)):
        return ()

    text = _strip_labels(block.text)
    sides = [part.strip() for part in text.split("=")]
    if len(sides) < 2:
        return ()

    dimensions = {entry.name: entry.dimension for entry in config.vars}
    aliases = {entry.alias: entry.canonical for entry in config.aliases}
    diagnostics: list[Diagnostic] = []
    for left_raw, right_raw in zip(sides, sides[1:], strict=False):
        left = _Parser(left_raw, block, text, dimensions, aliases, config).parse()
        right = _Parser(right_raw, block, text, dimensions, aliases, config).parse()
        diagnostics.extend(left.diagnostics)
        diagnostics.extend(right.diagnostics)
        if left.value is None or right.value is None or left.value == right.value:
            continue
        diagnostics.append(
            _diagnostic(block, text, "DIM001", _mismatch_detail(left.value, right.value))
        )
    return tuple(diagnostics)


@dataclass(frozen=True, slots=True)
class _DimensionResult:
    value: DimVector | None
    diagnostics: tuple[Diagnostic, ...] = ()


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

    def parse(self) -> _DimensionResult:
        if not self.tokens:
            return self._skipped()
        result = self._expr()
        if self._peek() is not None:
            return self._combine(result, self._skipped())
        return result

    def _expr(self) -> _DimensionResult:
        value = self._term()
        while self._peek() in {"+", "-"}:
            self._take()
            value = self._add_sub(value, self._term())
        return value

    def _term(self) -> _DimensionResult:
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

    def _power(self) -> _DimensionResult:
        value = self._atom()
        if self._peek() != "^":
            return value
        self._take()
        exponent = self._signed_integer()
        if exponent is None or value.value is None:
            return self._combine(value, self._skipped())
        return self._with_diagnostics(_scale(value.value, exponent), value.diagnostics)

    def _atom(self) -> _DimensionResult:
        token = self._take()
        if token is None:
            return self._skipped()
        if token == "+":
            return self._atom()
        if token == "-":
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
            return _DimensionResult(_DIMENSIONLESS)
        if _is_symbol_token(token) or token in self.aliases:
            return self._symbol(token)
        return self._skipped()

    def _group(self) -> _DimensionResult:
        if self._peek() != "(":
            return self._skipped()
        return self._atom()

    def _sqrt(self, value: _DimensionResult) -> _DimensionResult:
        if value.value is None:
            return value
        if any(exponent % 2 for exponent in value.value.exponents):
            return self._combine(value, self._skipped())
        return self._with_diagnostics(_scale(value.value, 1, divisor=2), value.diagnostics)

    def _symbol(self, name: str) -> _DimensionResult:
        canonical = self.aliases.get(name, name)
        dimension = self.dimensions.get(canonical)
        if dimension is not None:
            return _DimensionResult(dimension)
        if self.config.checks.dimension.unknown_variables == "ignore":
            return _DimensionResult(None)
        return _DimensionResult(None, (_diagnostic(self.block, self.equation, "DIM010", name),))

    def _add_sub(self, left: _DimensionResult, right: _DimensionResult) -> _DimensionResult:
        diagnostics = (*left.diagnostics, *right.diagnostics)
        if left.value is None or right.value is None:
            return _DimensionResult(None, diagnostics)
        if left.value != right.value:
            return _DimensionResult(
                None,
                (
                    *diagnostics,
                    _diagnostic(
                        self.block,
                        self.equation,
                        "DIM002",
                        _mismatch_detail(left.value, right.value),
                    ),
                ),
            )
        return _DimensionResult(left.value, diagnostics)

    def _mul(
        self,
        left: _DimensionResult,
        right: _DimensionResult,
        right_sign: int,
    ) -> _DimensionResult:
        diagnostics = (*left.diagnostics, *right.diagnostics)
        if left.value is None or right.value is None:
            return _DimensionResult(None, diagnostics)
        return _DimensionResult(_combine_vectors(left.value, right.value, right_sign), diagnostics)

    def _combine(self, left: _DimensionResult, right: _DimensionResult) -> _DimensionResult:
        return _DimensionResult(None, (*left.diagnostics, *right.diagnostics))

    def _skipped(self) -> _DimensionResult:
        return _DimensionResult(None, (_diagnostic(self.block, self.equation, "DIM020"),))

    def _with_diagnostics(
        self,
        value: DimVector,
        diagnostics: tuple[Diagnostic, ...],
    ) -> _DimensionResult:
        return _DimensionResult(value, diagnostics)

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


def _strip_labels(text: str) -> str:
    stripped = re.sub(r"^[ \t]*:label:[^\n]*\n?", "", text, flags=re.MULTILINE)
    return re.sub(r"\\label\{[^{}]+}", "", stripped).strip()


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


def _mismatch_detail(left: DimVector, right: DimVector) -> str:
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
