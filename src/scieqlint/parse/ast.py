"""AST contracts for v0.1.0 parser work."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from scieqlint.diag.model import SourceSpan


class BinaryOperator(Enum):
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    DIV = "div"
    POW = "pow"


class UnaryOperator(Enum):
    POS = "pos"
    NEG = "neg"


class FunctionName(Enum):
    SQRT = "sqrt"


class Expr: ...


@dataclass(frozen=True, slots=True)
class EquationGroup:
    equations: tuple[Equation, ...]
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class Equation:
    sides: tuple[Expr, ...]
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class Number(Expr):
    value: Fraction
    raw: str
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class Symbol(Expr):
    name: str
    raw: str
    span: SourceSpan
