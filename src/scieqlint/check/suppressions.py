"""Suppression comment parsing and diagnostic matching."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import MathBlock

_MARKDOWN_RE = re.compile(
    r"<!--\s*scieqlint-disable-next-line\b\s*(?P<codes>[A-Za-z0-9_, \t-]*?)\s*-->"
)
_LATEX_RE = re.compile(r"scieqlint-disable-current-block\b\s*(?P<codes>[A-Za-z0-9_, \t-]*)")
_CODE_RE = re.compile(r"[A-Z]+[0-9]+")
_OPERAND_RE = re.compile(r"[^,\s]+")


@dataclass(frozen=True, slots=True)
class _Suppression:
    code: str
    path: str
    line_start: int
    line_end: int


def apply_suppressions(
    diagnostics: Sequence[Diagnostic],
    *,
    documents: Sequence[SourceDocument],
    blocks: Sequence[MathBlock],
) -> tuple[Diagnostic, ...]:
    """Mark diagnostics suppressed by supported source comments."""
    suppressions, warnings = _collect_suppressions(documents, blocks)
    marked = tuple(_apply_to_diagnostic(diagnostic, suppressions) for diagnostic in diagnostics)
    return (*marked, *warnings)


def _collect_suppressions(
    documents: Sequence[SourceDocument],
    blocks: Sequence[MathBlock],
) -> tuple[tuple[_Suppression, ...], tuple[Diagnostic, ...]]:
    suppressions: list[_Suppression] = []
    warnings: list[Diagnostic] = []
    blocks_by_path: dict[str, list[MathBlock]] = {}
    for block in blocks:
        blocks_by_path.setdefault(block.span.path.as_posix(), []).append(block)

    for document in documents:
        document_blocks = blocks_by_path.get(document.path.as_posix(), [])
        if document.kind is DocumentKind.MARKDOWN:
            parsed, unknown = _markdown_suppressions(document, document_blocks)
        elif document.kind is DocumentKind.LATEX:
            parsed, unknown = _latex_suppressions(document, document_blocks)
        else:
            continue
        suppressions.extend(parsed)
        warnings.extend(unknown)
    return tuple(suppressions), tuple(warnings)


def _markdown_suppressions(
    document: SourceDocument,
    blocks: Sequence[MathBlock],
) -> tuple[tuple[_Suppression, ...], tuple[Diagnostic, ...]]:
    suppressions: list[_Suppression] = []
    warnings: list[Diagnostic] = []
    for line_start, line_end in _line_ranges(document.text):
        line = document.text[line_start:line_end]
        for match in _MARKDOWN_RE.finditer(line):
            line_number, _col = document.line_index.position(line_start + match.start())
            parsed, unknown = _codes(
                document,
                line_start + match.start("codes"),
                match.group("codes"),
            )
            warnings.extend(unknown)
            target_start, target_end = _markdown_target_lines(blocks, line_number + 1)
            suppressions.extend(
                _Suppression(
                    code=code,
                    path=document.path.as_posix(),
                    line_start=target_start,
                    line_end=target_end,
                )
                for code in parsed
            )
    return tuple(suppressions), tuple(warnings)


def _markdown_target_lines(blocks: Sequence[MathBlock], target_line: int) -> tuple[int, int]:
    for block in blocks:
        if block.span.line in {target_line, target_line + 1}:
            return block.span.line, block.span.end_line
    return target_line, target_line


def _latex_suppressions(
    document: SourceDocument,
    blocks: Sequence[MathBlock],
) -> tuple[tuple[_Suppression, ...], tuple[Diagnostic, ...]]:
    suppressions: list[_Suppression] = []
    warnings: list[Diagnostic] = []
    for line_start, line_end in _line_ranges(document.text):
        comment_start = _comment_start(document.text[line_start:line_end])
        if comment_start is None:
            continue
        comment_offset = line_start + comment_start
        comment = document.text[comment_offset:line_end]
        match = _LATEX_RE.search(comment)
        if match is None:
            continue
        parsed, unknown = _codes(
            document,
            comment_offset + match.start("codes"),
            match.group("codes"),
        )
        warnings.extend(unknown)
        directive_line, _col = document.line_index.position(comment_offset + match.start())
        target = _containing_block(blocks, directive_line)
        if target is None:
            continue
        suppressions.extend(
            _Suppression(
                code=code,
                path=document.path.as_posix(),
                line_start=target.span.line,
                line_end=target.span.end_line,
            )
            for code in parsed
        )
    return tuple(suppressions), tuple(warnings)


def _codes(
    document: SourceDocument,
    codes_start: int,
    raw: str,
) -> tuple[tuple[str, ...], tuple[Diagnostic, ...]]:
    codes: list[str] = []
    warnings: list[Diagnostic] = []
    operands = tuple(_OPERAND_RE.finditer(raw))
    if not operands:
        return (), (_unknown_code_diagnostic(document, codes_start, codes_start, "<empty>"),)
    for match in operands:
        code = match.group(0).upper()
        if _CODE_RE.fullmatch(code) and code in CATALOG:
            codes.append(code)
        else:
            warnings.append(
                _unknown_code_diagnostic(
                    document,
                    codes_start + match.start(),
                    codes_start + match.end(),
                    code,
                )
            )
    return tuple(codes), tuple(warnings)


def _unknown_code_diagnostic(
    document: SourceDocument,
    start: int,
    end: int,
    code: str,
) -> Diagnostic:
    info = CATALOG["SUP001"]
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=info.message,
        span=_span(document, start, end),
        detail=code,
        rule="suppressions",
    )


def _apply_to_diagnostic(
    diagnostic: Diagnostic,
    suppressions: Sequence[_Suppression],
) -> Diagnostic:
    if diagnostic.span is None:
        return diagnostic
    if any(_matches(diagnostic, suppression) for suppression in suppressions):
        return replace(diagnostic, suppressed=True, suppression_reason="source comment")
    return diagnostic


def _matches(diagnostic: Diagnostic, suppression: _Suppression) -> bool:
    span = diagnostic.span
    return (
        span is not None
        and diagnostic.code == suppression.code
        and span.path.as_posix() == suppression.path
        and suppression.line_start <= span.line <= suppression.line_end
    )


def _containing_block(blocks: Sequence[MathBlock], line: int) -> MathBlock | None:
    for block in blocks:
        if block.span.line <= line <= block.span.end_line:
            return block
    return None


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


def _is_escaped(text: str, index: int) -> bool:
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return slash_count % 2 == 1


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
