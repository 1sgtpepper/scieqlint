"""Explicit symbol directive parsing."""

from __future__ import annotations

import re
from collections.abc import Callable

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.scan.base import SymbolDirective

_BODY_RE = re.compile(
    r"^(?P<symbol>[A-Za-z][A-Za-z0-9_]*|\\[A-Za-z]+)\s*=\s*"
    r"[^,]+?"
    r"(?:\s*,\s*dim\s*=\s*\"[^\"]+\")?\s*$"
)


def parse_symbol_directive(
    *,
    body: str,
    span: SourceSpan,
    make_span: Callable[[int, int], SourceSpan],
    body_start: int,
) -> tuple[SymbolDirective | None, Diagnostic | None]:
    normalized_body = body.strip()
    match = _BODY_RE.fullmatch(normalized_body)
    if match is None:
        return None, _malformed_symbol_directive(span)

    symbol = match.group("symbol").strip()
    leading_space = len(body) - len(body.lstrip())
    symbol_start = body_start + leading_space + normalized_body.find(match.group("symbol"))
    return (
        SymbolDirective(
            symbol=symbol,
            span=make_span(symbol_start, symbol_start + len(match.group("symbol"))),
        ),
        None,
    )


def _malformed_symbol_directive(span: SourceSpan) -> Diagnostic:
    info = CATALOG["SCAN010"]
    return Diagnostic(
        code="SCAN010",
        severity=info.severity,
        message=info.message,
        span=span,
        rule="scanner",
    )
