"""LaTeX source scanner for supported math containers."""

from __future__ import annotations

import re
from collections.abc import Iterable

from scieqlint.config.model import Config
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.io.source import SourceDocument
from scieqlint.scan.base import MathBlock, MathContainer, ScanResult

ENV_RE = re.compile(r"\\begin\{(?P<name>equation\*?|align\*?)\}")
VERBATIM_RE = re.compile(r"\\begin\{verbatim\}.*?\\end\{verbatim\}", re.DOTALL)


class LatexScanner:
    def scan(self, document: SourceDocument, config: Config) -> ScanResult:
        _ = config
        ignored = _ignored_ranges(document)
        blocks: list[MathBlock] = []
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

        return ScanResult(
            blocks=tuple(sorted(blocks, key=lambda block: block.span.start)),
            diagnostics=tuple(sorted(diagnostics, key=_diagnostic_key)),
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
        if _in_ranges(start, ignored) or _is_escaped_opening(document.text, start, opening):
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
        if _in_ranges(match.start(), ignored):
            continue
        name = match.group("name")
        close_pattern = f"\\end{{{name}}}"
        close = _find_close(document, match.end(), close_pattern, ignored)
        if close == -1:
            diagnostics.append(_scan_diagnostic(document, match.start(), match.end()))
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
        span = _span(document, row_start, row_end)
        yield MathBlock(
            text=text,
            span=span,
            block_id=_block_id(document, span, MathContainer.LATEX_ALIGN),
            container=MathContainer.LATEX_ALIGN,
        )


def _align_rows(text: str, start: int, end: int) -> Iterable[tuple[int, int]]:
    row_start = start
    cursor = start
    while cursor < end:
        if text.startswith(r"\\", cursor) and not _is_escaped(text, cursor):
            yield _trim_span(text, row_start, cursor)
            row_start = _row_break_end(text, cursor + 2, end)
            cursor = row_start
            continue
        cursor += 1
    yield _trim_span(text, row_start, end)


def _math_block(
    document: SourceDocument,
    start: int,
    end: int,
    container: MathContainer,
) -> MathBlock | None:
    text = _clean_math_text(document.text[start:end])
    if not text:
        return None
    span_start, span_end = _trim_span(document.text, start, end)
    span = _span(document, span_start, span_end)
    return MathBlock(
        text=text,
        span=span,
        block_id=_block_id(document, span, container),
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
        if char == "%" and not _is_escaped(line, index):
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
            _in_ranges(start, ignored)
            or _is_escaped_opening(document.text, start, opening)
            or any(range_start <= start < range_end for range_start, range_end in closed)
        ):
            cursor = start + len(opening)
            continue
        if _find_close(document, start + len(opening), closing, ignored) == -1:
            yield _scan_diagnostic(document, start, start + len(opening))
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
        if _in_ranges(start, ignored) or _is_escaped_opening(document.text, start, opening):
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
        if not _in_ranges(close, ignored):
            return close
        cursor = close + len(closing)


def _ignored_ranges(document: SourceDocument) -> tuple[tuple[int, int], ...]:
    ranges = [(match.start(), match.end()) for match in VERBATIM_RE.finditer(document.text)]
    for line_start, line_end in _line_ranges(document.text):
        comment_start = _comment_start(document.text[line_start:line_end])
        if comment_start is not None:
            ranges.append((line_start + comment_start, line_end))
    return tuple(sorted(ranges))


def _line_ranges(text: str) -> Iterable[tuple[int, int]]:
    start = 0
    for line in text.splitlines(keepends=True):
        end = start + len(line)
        yield start, end
        start = end
    if start < len(text):
        yield start, len(text)


def _comment_start(line: str) -> int | None:
    for index, char in enumerate(line):
        if char == "%" and not _is_escaped(line, index):
            return index
    return None


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _row_break_end(text: str, start: int, end: int) -> int:
    if start < end and text[start] == "[":
        close = text.find("]", start + 1, end)
        newline = text.find("\n", start, end)
        if close != -1 and (newline == -1 or close < newline):
            return close + 1
    return start


def _is_escaped_opening(text: str, index: int, opening: str) -> bool:
    return opening.startswith("\\") and _is_escaped(text, index)


def _is_escaped(text: str, index: int) -> bool:
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return slash_count % 2 == 1


def _in_ranges(position: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= position < end for start, end in ranges)


def _diagnostic_key(diagnostic: Diagnostic) -> int:
    return diagnostic.span.start if diagnostic.span is not None else 0


def _block_id(
    document: SourceDocument,
    span: SourceSpan,
    container: MathContainer,
) -> str:
    return f"{document.display_path}:{span.line}:{span.col}:{container.value}"


def _span(document: SourceDocument, start: int, end: int) -> SourceSpan:
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


def _scan_diagnostic(document: SourceDocument, start: int, end: int) -> Diagnostic:
    info = CATALOG["SCAN001"]
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=info.message,
        span=_span(document, start, end),
        rule="scanner",
    )
