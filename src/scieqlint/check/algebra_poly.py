"""Exact polynomial operations used by the algebra checker."""

from __future__ import annotations

from fractions import Fraction
from math import isqrt

Monomial = tuple[tuple[str, int], ...]
Polynomial = dict[Monomial, Fraction]


class UnsupportedExpressionError(ValueError):
    def __init__(self, message: str, *, code: str = "PARSE020") -> None:
        super().__init__(message)
        self.code = code


def add(left: Polynomial, right: Polynomial) -> Polynomial:
    result = dict(left)
    for monomial, coefficient in right.items():
        result[monomial] = result.get(monomial, Fraction(0)) + coefficient
    return clean(result)


def sub(left: Polynomial, right: Polynomial) -> Polynomial:
    return add(left, neg(right))


def neg(value: Polynomial) -> Polynomial:
    return {monomial: -coefficient for monomial, coefficient in value.items()}


def mul(left: Polynomial, right: Polynomial) -> Polynomial:
    result: Polynomial = {}
    for left_monomial, left_coefficient in left.items():
        for right_monomial, right_coefficient in right.items():
            monomial = _merge_monomials(left_monomial, right_monomial)
            result[monomial] = (
                result.get(monomial, Fraction(0)) + left_coefficient * right_coefficient
            )
    return clean(result)


def div(left: Polynomial, right: Polynomial) -> Polynomial:
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


def pow_poly(value: Polynomial, exponent: int) -> Polynomial:
    result: Polynomial = {(): Fraction(1)}
    base = value if exponent >= 0 else div({(): Fraction(1)}, value)
    for _ in range(abs(exponent)):
        result = mul(result, base)
    return result


def sqrt_poly(value: Polynomial) -> Polynomial:
    square_root = _square_root(value)
    if square_root is not None:
        return square_root
    raise UnsupportedExpressionError("sqrt of non-square expression")


def symbols(value: Polynomial) -> set[str]:
    return {name for monomial in value for name, _power in monomial}


def clean(value: Polynomial) -> Polynomial:
    return {monomial: coefficient for monomial, coefficient in value.items() if coefficient}


def format_poly(value: Polynomial) -> str:
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


def _square_root(value: Polynomial) -> Polynomial | None:
    if len(value) != 1:
        return _binomial_square_root(value)
    monomial, coefficient = next(iter(value.items()))
    root = _integer_sqrt(coefficient)
    if root is None:
        return None
    factors: list[tuple[str, int]] = []
    for name, power in monomial:
        if power % 2:
            return None
        factors.append((name, power // 2))
    return {tuple(factors): root}


def _binomial_square_root(value: Polynomial) -> Polynomial | None:
    if len(value) != 3:
        return None
    for monomial, coefficient in value.items():
        if coefficient <= 0:
            continue
        first = _square_root({monomial: coefficient})
        if first is None:
            continue
        remaining = sub(value, pow_poly(first, 2))
        for other_monomial, other_coefficient in remaining.items():
            if other_coefficient <= 0:
                continue
            second = _square_root({other_monomial: other_coefficient})
            if second is None:
                continue
            for root in (add(first, second), sub(first, second)):
                if clean(sub(pow_poly(root, 2), value)) == {}:
                    return root
    return None


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
