"""Shared helpers for LaTeX scanner source ranges and diagnostics."""

from __future__ import annotations

import re
from collections.abc import Iterable

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.io.source import SourceDocument
from scieqlint.scan.base import MathContainer

VERBATIM_RE = re.compile(r"\\begin\{verbatim\}.*?\\end\{verbatim\}", re.DOTALL)


def ignored_ranges(document: SourceDocument) -> tuple[tuple[int, int], ...]:
    ranges = list(verbatim_ranges(document))
    for line_start, line_end in line_ranges(document.text):
        comment_start = comment_start_index(document.text[line_start:line_end])
        if comment_start is not None:
            ranges.append((line_start + comment_start, line_end))
    return tuple(sorted(ranges))


def verbatim_ranges(document: SourceDocument) -> tuple[tuple[int, int], ...]:
    return tuple((match.start(), match.end()) for match in VERBATIM_RE.finditer(document.text))


def line_ranges(text: str) -> Iterable[tuple[int, int]]:
    start = 0
    for line in text.splitlines(keepends=True):
        end = start + len(line)
        yield start, end
        start = end
    if start < len(text):
        yield start, len(text)


def comment_start_index(line: str) -> int | None:
    for index, char in enumerate(line):
        if char == "%" and not is_escaped(line, index):
            return index
    return None


def trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def row_break_end(text: str, start: int, end: int) -> int:
    if start < end and text[start] == "[":
        close = text.find("]", start + 1, end)
        newline = text.find("\n", start, end)
        if close != -1 and (newline == -1 or close < newline):
            return close + 1
    return start


def is_escaped_opening(text: str, index: int, opening: str) -> bool:
    return opening.startswith("\\") and is_escaped(text, index)


def is_escaped(text: str, index: int) -> bool:
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return slash_count % 2 == 1


def in_ranges(position: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= position < end for start, end in ranges)


def normalize_label(value: str) -> str:
    value = value.strip()
    return value[1:] if value.startswith("#") else value


def diagnostic_key(diagnostic: Diagnostic) -> int:
    return diagnostic.span.start if diagnostic.span is not None else 0


def block_id(
    document: SourceDocument,
    span: SourceSpan,
    container: MathContainer,
) -> str:
    return f"{document.display_path}:{span.line}:{span.col}:{container.value}"


def span(document: SourceDocument, start: int, end: int) -> SourceSpan:
    line, col = document.line_index.position(start)
    end_line, end_col = document.line_index.position(max(start, end - 1))
    return SourceSpan(
        path=document.path,
        start=start,
        end=end,
        line=line,
        col=col,
        end_line=end_line,
        end_col=end_col,
    )


def scan_diagnostic(document: SourceDocument, start: int, end: int) -> Diagnostic:
    info = CATALOG["SCAN001"]
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=info.message,
        span=span(document, start, end),
        rule="scanner",
    )
