"""Explicit symbol-table checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.scan.base import MathBlock, SymbolDirective

SYMBOL_RE = re.compile(r"\\[A-Za-z]+|[A-Za-z][A-Za-z0-9_]*")
TEX_NON_SYMBOLS = {
    "\\cdot",
    "\\frac",
    "\\sqrt",
    "\\times",
    "\\sin",
    "\\cos",
    "\\tan",
    "\\log",
    "\\ln",
    "\\exp",
}


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
    source = block.source_aligned_text
    text = _strip_labels(source)
    symbols: list[tuple[str, SourceSpan]] = []
    offset = 0
    for line_delta, line in enumerate(source.splitlines(keepends=True)):
        line_end = offset + len(line)
        for match in SYMBOL_RE.finditer(text, offset, line_end):
            symbol = match.group(0)
            if symbol in TEX_NON_SYMBOLS:
                continue
            symbols.append(
                (
                    symbol,
                    _span_from_block(
                        block,
                        match.start(),
                        match.end(),
                        line_delta=line_delta,
                    ),
                )
            )
        offset = line_end
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


def _span_from_block(
    block: MathBlock,
    start: int,
    end: int,
    *,
    line_delta: int,
) -> SourceSpan:
    if start < 0 or end < start or end > len(block.source_aligned_text):
        raise ValueError("block logical range is outside its source")
    if block.span.segments:
        segments = block.span.segments[start:end]
        if len(segments) != end - start or not segments:
            raise ValueError("block logical range does not match its source segments")
        first = segments[0]
        last = segments[-1]
        return SourceSpan(
            path=block.span.path,
            start=first.start,
            end=last.end,
            line=first.line,
            col=first.col,
            end_line=last.end_line,
            end_col=last.end_col,
            cell=block.span.cell,
            cell_line=(None if block.span.cell_line is None else block.span.cell_line + line_delta),
            segments=segments,
        )
    raw_start = block.span.start + start
    raw_end = block.span.start + end
    line_delta, col = _position_from_block(block, raw_start)
    end_line_delta, end_col = _position_from_block(block, max(raw_start, raw_end - 1))
    return SourceSpan(
        path=block.span.path,
        start=raw_start,
        end=raw_end,
        line=block.span.line + line_delta,
        col=col,
        end_line=block.span.line + end_line_delta,
        end_col=end_col,
        cell=block.span.cell,
        cell_line=None if block.span.cell_line is None else block.span.cell_line + line_delta,
    )


def _position_from_block(block: MathBlock, offset: int) -> tuple[int, int]:
    relative = offset - block.span.start
    line_delta = block.source_aligned_text[:relative].count("\n")
    if line_delta == 0:
        return line_delta, block.span.col + relative
    return line_delta, relative - block.source_aligned_text.rfind("\n", 0, relative)


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
