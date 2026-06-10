"""Markdown and MyST scanner for the v0.1 subset."""

from __future__ import annotations

import re
from collections.abc import Iterable

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
CODE_FENCE_RE = re.compile(
    r"^```(?!math|\{math\})[^\n]*\n.*?^```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
FENCE_RE = re.compile(
    r"^```(?P<kind>math|\{math\})[ \t]*\n(?P<body>.*?)(?P<close>^```[ \t]*$)",
    re.MULTILINE | re.DOTALL,
)


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

        references = tuple(_references(document))
        symbol_directives, symbol_diagnostics = _symbol_directives(document, _code_spans(document))
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
    for match in FENCE_RE.finditer(document.text):
        body = match.group("body")
        text = body.strip()
        body_start = match.start("body") + len(body) - len(body.lstrip())
        body_end = match.start("body") + len(body.rstrip())
        span = _span(document, body_start, body_end)
        yield MathBlock(
            text=text,
            span=span,
            block_id=_block_id(document, span, MathContainer.MARKDOWN_FENCE),
            container=MathContainer.MARKDOWN_FENCE,
        )


def _unterminated_fence_diagnostics(document: SourceDocument) -> Iterable[Diagnostic]:
    closed = {(match.start(), match.end()) for match in FENCE_RE.finditer(document.text)}
    for match in re.finditer(r"^```(?:math|\{math\})[ \t]*$", document.text, re.MULTILINE):
        if any(start <= match.start() < end for start, end in closed):
            continue
        next_close = re.search(r"^```[ \t]*$", document.text[match.end() :], re.MULTILINE)
        if next_close is None:
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
        *((match.start(), match.end()) for match in CODE_FENCE_RE.finditer(document.text)),
    )
