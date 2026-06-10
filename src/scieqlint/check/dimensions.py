"""Configured physical-dimension checks."""

from __future__ import annotations

import re

from scieqlint.check.dimensions_parser import (
    mismatch_detail,
    parse_dimension_expression,
)
from scieqlint.config.model import Config
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic
from scieqlint.scan.base import MathBlock


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
        left = parse_dimension_expression(left_raw, block, text, dimensions, aliases, config)
        right = parse_dimension_expression(right_raw, block, text, dimensions, aliases, config)
        diagnostics.extend(left.diagnostics)
        diagnostics.extend(right.diagnostics)
        if left.value is None or right.value is None or left.value == right.value:
            continue
        diagnostics.append(
            _diagnostic(block, text, "DIM001", mismatch_detail(left.value, right.value))
        )
    return tuple(diagnostics)


def _strip_labels(text: str) -> str:
    stripped = re.sub(r"^[ \t]*:label:[^\n]*\n?", "", text, flags=re.MULTILINE)
    return re.sub(r"\\label\{[^{}]+}", "", stripped).strip()


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
