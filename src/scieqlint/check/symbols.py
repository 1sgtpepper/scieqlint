"""Explicit symbol-table checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.scan.base import MathBlock, SymbolDirective

SYMBOL_RE = re.compile(r"\\[A-Za-z]+|[A-Za-z][A-Za-z0-9_]*")
TEX_NON_SYMBOLS = {"\\cdot", "\\frac", "\\sqrt", "\\times"}


def check_symbols(
    blocks: tuple[MathBlock, ...],
    directives: tuple[SymbolDirective, ...],
    *,
    path_order: dict[str, int] | None = None,
) -> tuple[Diagnostic, ...]:
    defined: set[str] = set()
    reported: set[str] = set()
    diagnostics: list[Diagnostic] = []

    events = [*_directive_events(directives), *_block_events(blocks)]
    for event in sorted(events, key=lambda event: _event_key(event, path_order)):
        if event.kind == "directive":
            defined.add(event.symbol)
            continue
        for symbol, span in _symbols(event.block):
            if symbol in defined or symbol in reported:
                continue
            reported.add(symbol)
            diagnostics.append(_undefined_symbol(symbol, span))
    return tuple(diagnostics)


@dataclass(frozen=True, slots=True)
class _Event:
    kind: Literal["directive", "block"]
    span: SourceSpan
    symbol: str = ""
    block: MathBlock | None = None


def _directive_events(directives: tuple[SymbolDirective, ...]) -> list[_Event]:
    return [
        _Event(kind="directive", span=directive.span, symbol=directive.symbol)
        for directive in directives
    ]


def _block_events(blocks: tuple[MathBlock, ...]) -> list[_Event]:
    return [_Event(kind="block", span=block.span, block=block) for block in blocks]


def _symbols(block: MathBlock | None) -> tuple[tuple[str, SourceSpan], ...]:
    if block is None:
        return ()
    text = _strip_labels(block.text)
    symbols: list[tuple[str, SourceSpan]] = []
    for match in SYMBOL_RE.finditer(text):
        symbol = match.group(0)
        if symbol in TEX_NON_SYMBOLS:
            continue
        start = block.span.start + match.start()
        end = block.span.start + match.end()
        symbols.append((symbol, _span_from_block(block, start, end)))
    return tuple(symbols)


def _strip_labels(text: str) -> str:
    stripped = re.sub(
        r"^[ \t]*:label:[^\n]*\n?",
        lambda match: _spaces(match.group(0)),
        text,
        flags=re.MULTILINE,
    )
    return re.sub(r"\\label\{[^{}]+}", lambda match: _spaces(match.group(0)), stripped)


def _spaces(value: str) -> str:
    return "".join("\n" if char == "\n" else " " for char in value)


def _span_from_block(block: MathBlock, start: int, end: int) -> SourceSpan:
    line_delta, col = _position_from_block(block, start)
    end_line_delta, end_col = _position_from_block(block, max(start, end - 1))
    return SourceSpan(
        path=block.span.path,
        start=start,
        end=end,
        line=block.span.line + line_delta,
        col=col,
        end_line=block.span.line + end_line_delta,
        end_col=end_col,
        cell=block.span.cell,
        cell_line=None if block.span.cell_line is None else block.span.cell_line + line_delta,
    )


def _position_from_block(block: MathBlock, offset: int) -> tuple[int, int]:
    relative = offset - block.span.start
    line_delta = block.text[:relative].count("\n")
    if line_delta == 0:
        return line_delta, block.span.col + relative
    return line_delta, relative - block.text.rfind("\n", 0, relative)


def _event_key(
    event: _Event,
    path_order: dict[str, int] | None,
) -> tuple[int, str, int, int, int, int, int]:
    span = event.span
    path = span.path.as_posix()
    order = path_order.get(path, 0) if path_order is not None else 0
    cell = -1 if span.cell is None else span.cell
    kind_order = 0 if event.kind == "directive" else 1
    return (order, path, cell, span.line, span.col, kind_order, span.start)


def _undefined_symbol(symbol: str, span: SourceSpan) -> Diagnostic:
    info = CATALOG["SYM001"]
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=f"{info.message}: {symbol}",
        span=span,
        detail=symbol,
        rule="symbols",
    )
