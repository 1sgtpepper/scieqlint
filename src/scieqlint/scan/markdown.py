"""Markdown and MyST scanner for the v0.1 subset."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from scieqlint.config.model import Config
from scieqlint.diag.model import Diagnostic
from scieqlint.io.source import SourceDocument
from scieqlint.scan.base import (
    EquationLabel,
    MathBlock,
    MathContainer,
    ScanResult,
)
from scieqlint.scan.markdown_semantics import (
    block_id as _block_id,
)
from scieqlint.scan.markdown_semantics import (
    display_tail_labels as _display_tail_labels,
)
from scieqlint.scan.markdown_semantics import (
    in_ranges as _in_ranges,
)
from scieqlint.scan.markdown_semantics import (
    myst_directive_labels as _myst_directive_labels,
)
from scieqlint.scan.markdown_semantics import (
    references as _references,
)
from scieqlint.scan.markdown_semantics import (
    scan_diagnostic as _scan_diagnostic,
)
from scieqlint.scan.markdown_semantics import (
    span as _span,
)
from scieqlint.scan.markdown_semantics import (
    symbol_directives as _symbol_directives,
)
from scieqlint.scan.markdown_semantics import (
    tex_labels as _tex_labels,
)

DISPLAY_RE = re.compile(r"\$\$(?P<body>.*?)(?P<close>\$\$)(?P<tail>[^\n]*)", re.DOTALL)
INLINE_RE = re.compile(r"(?<!\$)\$(?!\$)(?P<body>[^\n$]+?)(?<!\$)\$(?!\$)")
INLINE_CODE_RE = re.compile(r"(?P<ticks>`+)[^`\n]*(?P=ticks)")
CODE_FENCE_OPEN_RE = re.compile(r"^(?P<fence>`{3,})(?P<info>[^\n]*)$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class _CodeFence:
    start: int
    body_start: int
    body_end: int
    end: int
    info: str
    closed: bool


class MarkdownScanner:
    def scan(self, document: SourceDocument, config: Config) -> ScanResult:
        if not config.scanner.markdown:
            return ScanResult(blocks=())

        blocks: list[MathBlock] = []
        labels: list[EquationLabel] = []
        diagnostics: list[Diagnostic] = []

        for block in _display_blocks(document):
            blocks.append(block)
            labels.extend(_tex_labels(document, block))
            labels.extend(_display_tail_labels(document, block))
        diagnostics.extend(_unterminated_display_diagnostics(document))

        if config.scanner.math_fences:
            for block in _fenced_blocks(document):
                blocks.append(block)
                labels.extend(_tex_labels(document, block))
                labels.extend(_myst_directive_labels(document, block))
            diagnostics.extend(_unterminated_fence_diagnostics(document))

        if config.scanner.inline_math:
            blocks.extend(_inline_blocks(document, blocks))

        code_spans = _code_spans(document)
        references = tuple(_references(document, code_spans))
        symbol_directives, symbol_diagnostics = _symbol_directives(document, code_spans)
        diagnostics.extend(symbol_diagnostics)
        return ScanResult(
            blocks=tuple(sorted(blocks, key=lambda block: block.span.start)),
            labels=tuple(sorted(labels, key=lambda label: label.span.start)),
            references=references,
            symbol_directives=symbol_directives,
            diagnostics=tuple(diagnostics),
        )


def _display_blocks(document: SourceDocument) -> Iterable[MathBlock]:
    for _start, body_start, body_end, _end in _display_ranges(document):
        body = document.text[body_start:body_end]
        text = body.strip()
        span_start = body_start + len(body) - len(body.lstrip())
        span_end = body_start + len(body.rstrip())
        span = _span(document, span_start, span_end)
        yield MathBlock(
            text=text,
            span=span,
            block_id=_block_id(document, span, MathContainer.MARKDOWN_DISPLAY),
            container=MathContainer.MARKDOWN_DISPLAY,
        )


def _unterminated_display_diagnostics(document: SourceDocument) -> Iterable[Diagnostic]:
    closed = {(start, end) for start, _body_start, _body_end, end in _display_ranges(document)}
    occupied = _code_spans(document)
    for match in re.finditer(r"\$\$", document.text):
        if any(start <= match.start() < end for start, end in closed):
            continue
        if any(start <= match.start() < end for start, end in occupied):
            continue
        next_close = _find_display_close(document, match.end(), occupied)
        if next_close == -1:
            yield _scan_diagnostic(document, match.start(), match.end())


def _display_ranges(document: SourceDocument) -> Iterable[tuple[int, int, int, int]]:
    occupied = _code_spans(document)
    cursor = 0
    while True:
        start = document.text.find("$$", cursor)
        if start == -1:
            return
        if _in_ranges(start, occupied):
            cursor = start + 2
            continue
        close = _find_display_close(document, start + 2, occupied)
        if close == -1:
            cursor = start + 2
            continue
        yield (start, start + 2, close, close + 2)
        cursor = close + 2


def _find_display_close(
    document: SourceDocument,
    start: int,
    occupied: tuple[tuple[int, int], ...],
) -> int:
    cursor = start
    while True:
        close = document.text.find("$$", cursor)
        if close == -1:
            return -1
        if not _in_ranges(close, occupied):
            return close
        cursor = close + 2


def _fenced_blocks(document: SourceDocument) -> Iterable[MathBlock]:
    for fence in _code_fences(document):
        if not fence.closed or not _is_math_fence_info(fence.info):
            continue
        body = document.text[fence.body_start : fence.body_end]
        text = body.strip()
        body_start = fence.body_start + len(body) - len(body.lstrip())
        body_end = fence.body_start + len(body.rstrip())
        span = _span(document, body_start, body_end)
        yield MathBlock(
            text=text,
            span=span,
            block_id=_block_id(document, span, MathContainer.MARKDOWN_FENCE),
            container=MathContainer.MARKDOWN_FENCE,
        )


def _unterminated_fence_diagnostics(document: SourceDocument) -> Iterable[Diagnostic]:
    closed = {
        (fence.start, fence.end)
        for fence in _code_fences(document)
        if fence.closed and _is_math_fence_info(fence.info)
    }
    occupied = _non_math_code_fences(document)
    for match in CODE_FENCE_OPEN_RE.finditer(document.text):
        if not _is_math_fence_info(match.group("info")):
            continue
        if any(start <= match.start() < end for start, end in closed):
            continue
        if _in_ranges(match.start(), occupied):
            continue
        body_start = _fence_body_start(document.text, match.end())
        if _find_code_fence_close(document.text, body_start, len(match.group("fence"))) is None:
            yield _scan_diagnostic(document, match.start(), match.end())


def _inline_blocks(
    document: SourceDocument,
    existing_blocks: list[MathBlock],
) -> Iterable[MathBlock]:
    occupied = (
        *((block.span.start, block.span.end) for block in existing_blocks),
        *_code_spans(document),
    )
    for match in INLINE_RE.finditer(document.text):
        body_start = match.start("body")
        body_end = match.end("body")
        if any(start <= body_start < end for start, end in occupied):
            continue
        body = match.group("body")
        span = _span(document, body_start, body_end)
        yield MathBlock(
            text=body.strip(),
            span=span,
            block_id=_block_id(document, span, MathContainer.MARKDOWN_INLINE),
            container=MathContainer.MARKDOWN_INLINE,
        )


def _code_spans(document: SourceDocument) -> tuple[tuple[int, int], ...]:
    return (
        *((match.start(), match.end()) for match in INLINE_CODE_RE.finditer(document.text)),
        *_non_math_code_fences(document),
    )


def _non_math_code_fences(document: SourceDocument) -> tuple[tuple[int, int], ...]:
    return tuple(
        (fence.start, fence.end)
        for fence in _code_fences(document)
        if not _is_math_fence_info(fence.info)
    )


def _is_math_fence_info(info: str) -> bool:
    return info.strip() in {"math", "{math}"}


def _code_fences(document: SourceDocument) -> Iterable[_CodeFence]:
    cursor = 0
    while True:
        match = CODE_FENCE_OPEN_RE.search(document.text, cursor)
        if match is None:
            return
        opener_length = len(match.group("fence"))
        body_start = _fence_body_start(document.text, match.end())
        close = _find_code_fence_close(document.text, body_start, opener_length)
        if close is None:
            if not _is_math_fence_info(match.group("info")):
                yield _CodeFence(
                    start=match.start(),
                    body_start=body_start,
                    body_end=len(document.text),
                    end=len(document.text),
                    info=match.group("info"),
                    closed=False,
                )
                return
            cursor = body_start
            continue
        close_start, close_end = close
        yield _CodeFence(
            start=match.start(),
            body_start=body_start,
            body_end=close_start,
            end=close_end,
            info=match.group("info"),
            closed=True,
        )
        cursor = close_end


def _fence_body_start(text: str, opening_line_end: int) -> int:
    if opening_line_end < len(text) and text[opening_line_end] == "\n":
        return opening_line_end + 1
    return opening_line_end


def _find_code_fence_close(
    text: str,
    start: int,
    opener_length: int,
) -> tuple[int, int] | None:
    close_re = re.compile(rf"^`{{{opener_length},}}[ \t]*$", re.MULTILINE)
    match = close_re.search(text, start)
    if match is None:
        return None
    return (match.start(), match.end())
