"""LaTeX source scanner for supported math containers."""

from __future__ import annotations

import re
from collections.abc import Iterable

from scieqlint.config.model import Config
from scieqlint.diag.model import Diagnostic
from scieqlint.io.source import SourceDocument
from scieqlint.scan import latex_support as support
from scieqlint.scan.base import (
    EquationLabel,
    MathBlock,
    MathContainer,
    ScanResult,
)
from scieqlint.scan.latex_semantics import labels as _labels
from scieqlint.scan.latex_semantics import references as _references
from scieqlint.scan.latex_symbols import symbol_directives as _symbol_directives

ENV_RE = re.compile(r"\\begin\{(?P<name>equation\*?|align\*?)\}")


class LatexScanner:
    def scan(self, document: SourceDocument, config: Config) -> ScanResult:
        _ = config
        verbatim = support.verbatim_ranges(document)
        ignored = support.ignored_ranges(document)
        blocks: list[MathBlock] = []
        labels: list[EquationLabel] = []
        diagnostics: list[Diagnostic] = []

        blocks.extend(
            _delimited_blocks(document, ignored, r"\[", r"\]", MathContainer.LATEX_DISPLAY)
        )
        blocks.extend(_delimited_blocks(document, ignored, "$$", "$$", MathContainer.LATEX_DISPLAY))
        env_blocks, env_diagnostics = _environment_blocks(document, ignored)
        blocks.extend(env_blocks)
        diagnostics.extend(env_diagnostics)
        diagnostics.extend(_unterminated_delimiters(document, ignored, r"\[", r"\]"))
        diagnostics.extend(_unterminated_delimiters(document, ignored, "$$", "$$"))
        labels.extend(_labels(document, blocks, ignored))
        references = tuple(_references(document, ignored))
        symbol_directives, symbol_diagnostics = _symbol_directives(document, verbatim)
        diagnostics.extend(symbol_diagnostics)

        return ScanResult(
            blocks=tuple(sorted(blocks, key=lambda block: block.span.start)),
            labels=tuple(sorted(labels, key=lambda label: label.span.start)),
            references=references,
            symbol_directives=symbol_directives,
            diagnostics=tuple(sorted(diagnostics, key=support.diagnostic_key)),
        )


def _delimited_blocks(
    document: SourceDocument,
    ignored: tuple[tuple[int, int], ...],
    opening: str,
    closing: str,
    container: MathContainer,
) -> Iterable[MathBlock]:
    cursor = 0
    while True:
        start = document.text.find(opening, cursor)
        if start == -1:
            return
        if support.in_ranges(start, ignored) or support.is_escaped_opening(
            document.text, start, opening
        ):
            cursor = start + len(opening)
            continue
        body_start = start + len(opening)
        close = _find_close(document, body_start, closing, ignored)
        if close == -1:
            cursor = body_start
            continue
        block = _math_block(document, body_start, close, container)
        if block is not None:
            yield block
        cursor = close + len(closing)


def _environment_blocks(
    document: SourceDocument,
    ignored: tuple[tuple[int, int], ...],
) -> tuple[list[MathBlock], list[Diagnostic]]:
    blocks: list[MathBlock] = []
    diagnostics: list[Diagnostic] = []
    for match in ENV_RE.finditer(document.text):
        if support.in_ranges(match.start(), ignored):
            continue
        name = match.group("name")
        close_pattern = f"\\end{{{name}}}"
        close = _find_close(document, match.end(), close_pattern, ignored)
        if close == -1:
            diagnostics.append(support.scan_diagnostic(document, match.start(), match.end()))
            continue
        container = (
            MathContainer.LATEX_ALIGN if name.startswith("align") else MathContainer.LATEX_EQUATION
        )
        if container is MathContainer.LATEX_ALIGN:
            blocks.extend(_align_blocks(document, match.end(), close))
        else:
            block = _math_block(document, match.end(), close, container)
            if block is not None:
                blocks.append(block)
    return blocks, diagnostics


def _align_blocks(document: SourceDocument, start: int, end: int) -> Iterable[MathBlock]:
    for row_start, row_end in _align_rows(document.text, start, end):
        text = _clean_math_text(document.text[row_start:row_end]).replace("&", "").strip()
        if not text:
            continue
        span = support.span(document, row_start, row_end)
        yield MathBlock(
            text=text,
            span=span,
            block_id=support.block_id(document, span, MathContainer.LATEX_ALIGN),
            container=MathContainer.LATEX_ALIGN,
        )


def _align_rows(text: str, start: int, end: int) -> Iterable[tuple[int, int]]:
    row_start = start
    cursor = start
    while cursor < end:
        if text.startswith(r"\\", cursor) and not support.is_escaped(text, cursor):
            yield support.trim_span(text, row_start, cursor)
            row_start = support.row_break_end(text, cursor + 2, end)
            cursor = row_start
            continue
        cursor += 1
    yield support.trim_span(text, row_start, end)


def _math_block(
    document: SourceDocument,
    start: int,
    end: int,
    container: MathContainer,
) -> MathBlock | None:
    text = _clean_math_text(document.text[start:end])
    if not text:
        return None
    span_start, span_end = support.trim_span(document.text, start, end)
    span = support.span(document, span_start, span_end)
    return MathBlock(
        text=text,
        span=span,
        block_id=support.block_id(document, span, container),
        container=container,
    )


def _clean_math_text(text: str) -> str:
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        cleaned = _strip_comment(line).strip()
        if cleaned:
            cleaned_lines.append(cleaned)
    return "\n".join(cleaned_lines)


def _strip_comment(line: str) -> str:
    for index, char in enumerate(line):
        if char == "%" and not support.is_escaped(line, index):
            return line[:index]
    return line


def _unterminated_delimiters(
    document: SourceDocument,
    ignored: tuple[tuple[int, int], ...],
    opening: str,
    closing: str,
) -> Iterable[Diagnostic]:
    closed = {
        (start, end)
        for start, _body_start, _body_end, end in _delimiter_ranges(
            document,
            ignored,
            opening,
            closing,
        )
    }
    cursor = 0
    while True:
        start = document.text.find(opening, cursor)
        if start == -1:
            return
        if (
            support.in_ranges(start, ignored)
            or support.is_escaped_opening(document.text, start, opening)
            or any(range_start <= start < range_end for range_start, range_end in closed)
        ):
            cursor = start + len(opening)
            continue
        if _find_close(document, start + len(opening), closing, ignored) == -1:
            yield support.scan_diagnostic(document, start, start + len(opening))
        cursor = start + len(opening)


def _delimiter_ranges(
    document: SourceDocument,
    ignored: tuple[tuple[int, int], ...],
    opening: str,
    closing: str,
) -> Iterable[tuple[int, int, int, int]]:
    cursor = 0
    while True:
        start = document.text.find(opening, cursor)
        if start == -1:
            return
        if support.in_ranges(start, ignored) or support.is_escaped_opening(
            document.text, start, opening
        ):
            cursor = start + len(opening)
            continue
        body_start = start + len(opening)
        close = _find_close(document, body_start, closing, ignored)
        if close == -1:
            cursor = body_start
            continue
        yield start, body_start, close, close + len(closing)
        cursor = close + len(closing)


def _find_close(
    document: SourceDocument,
    start: int,
    closing: str,
    ignored: tuple[tuple[int, int], ...],
) -> int:
    cursor = start
    while True:
        close = document.text.find(closing, cursor)
        if close == -1:
            return -1
        if not support.in_ranges(close, ignored):
            return close
        cursor = close + len(closing)
