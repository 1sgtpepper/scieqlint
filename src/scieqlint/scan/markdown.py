"""Markdown and MyST scanner for the v0.1 subset."""

from __future__ import annotations

import re
from collections.abc import Iterable

from scieqlint.config.model import Config
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.io.source import SourceDocument
from scieqlint.scan.base import (
    EquationLabel,
    EquationReference,
    LabelSource,
    MathBlock,
    MathContainer,
    ReferenceSource,
    ScanResult,
    SymbolDirective,
    SymbolDirectiveSource,
)
from scieqlint.scan.symbols import parse_symbol_directive

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
TEX_LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")
DOLLAR_LABEL_RE = re.compile(r"\{#([^}\s]+)\}|\(([^()\s]+)\)")
MYST_LABEL_RE = re.compile(r"^[ \t]*:label:[ \t]*(?P<label>\S+)[ \t]*$", re.MULTILINE)
MYST_ANCHOR_RE = re.compile(r"^[ \t]*\((?P<label>[^()\s]+)\)=[ \t]*$")
HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+\S")
MD_LINK_RE = re.compile(r"\[[^\]]*]\(#(?P<target>[^)\s]+)\)")
EQ_ROLE_RE = re.compile(r"\{(?P<role>eq|numref)\}`(?P<body>[^`]+)`")
SYMBOL_DIRECTIVE_RE = re.compile(
    r"<!--\s*scieqlint-symbol:\s*(?P<body>.*?)\s*-->",
    re.DOTALL,
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
        symbol_directives, symbol_diagnostics = _symbol_directives(document)
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


def _in_ranges(position: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= position < end for start, end in ranges)


def _tex_labels(document: SourceDocument, block: MathBlock) -> Iterable[EquationLabel]:
    for match in TEX_LABEL_RE.finditer(block.text):
        label_start = block.span.start + match.start(1)
        label_end = block.span.start + match.end(1)
        yield EquationLabel(
            label=_normalize_label(match.group(1)),
            span=_span(document, label_start, label_end),
            block_id=block.block_id,
            source=LabelSource.TEX_LABEL_IN_MARKDOWN_MATH,
        )


def _display_tail_labels(document: SourceDocument, block: MathBlock) -> Iterable[EquationLabel]:
    close_start = document.text.find("$$", block.span.end)
    if close_start == -1:
        return
    tail_start = close_start + 2
    line_end = document.text.find("\n", tail_start)
    if line_end == -1:
        line_end = len(document.text)
    tail = document.text[tail_start:line_end]
    for match in DOLLAR_LABEL_RE.finditer(tail):
        raw = match.group(1) or match.group(2)
        if raw is None:
            continue
        label_start = tail_start + match.start(1 if match.group(1) else 2)
        label_end = tail_start + match.end(1 if match.group(1) else 2)
        yield EquationLabel(
            label=_normalize_label(raw),
            span=_span(document, label_start, label_end),
            block_id=block.block_id,
            source=(
                LabelSource.MYST_DOLLAR_LABEL if match.group(2) else LabelSource.MARKDOWN_ANCHOR
            ),
        )


def _myst_directive_labels(document: SourceDocument, block: MathBlock) -> Iterable[EquationLabel]:
    for match in MYST_LABEL_RE.finditer(block.text):
        label_start = block.span.start + match.start("label")
        label_end = block.span.start + match.end("label")
        yield EquationLabel(
            label=_normalize_label(match.group("label")),
            span=_span(document, label_start, label_end),
            block_id=block.block_id,
            source=LabelSource.MYST_DIRECTIVE_LABEL,
        )


def _references(document: SourceDocument) -> Iterable[EquationReference]:
    attached_myst_anchors = _attached_myst_heading_anchor_targets(document)
    for match in MD_LINK_RE.finditer(document.text):
        target = _normalize_label(match.group("target"))
        if target in attached_myst_anchors:
            continue
        yield EquationReference(
            target=target,
            span=_span(document, match.start("target"), match.end("target")),
            raw=match.group(0),
            source=ReferenceSource.MARKDOWN_ANCHOR,
        )
    for match in EQ_ROLE_RE.finditer(document.text):
        role = match.group("role")
        body = match.group("body")
        target = _extract_role_target(body)
        source = ReferenceSource.MYST_EQ_ROLE if role == "eq" else ReferenceSource.MYST_NUMREF_ROLE
        target_start = match.start("body") + body.rfind(target)
        yield EquationReference(
            target=_normalize_label(target),
            span=_span(document, target_start, target_start + len(target)),
            raw=match.group(0),
            source=source,
        )


def _attached_myst_heading_anchor_targets(document: SourceDocument) -> frozenset[str]:
    occupied = _code_spans(document)
    lines = _line_ranges(document.text)
    targets: set[str] = set()
    for index, (start, _end, line) in enumerate(lines):
        if _in_ranges(start, occupied):
            continue
        match = MYST_ANCHOR_RE.match(line)
        if match is None:
            continue
        next_index = _next_attachable_line_index(lines, index + 1)
        if next_index is not None and HEADING_RE.match(lines[next_index][2]) is not None:
            targets.add(_normalize_label(match.group("label")))
    return frozenset(targets)


def _next_attachable_line_index(
    lines: tuple[tuple[int, int, str], ...],
    index: int,
) -> int | None:
    while index < len(lines):
        line = lines[index][2].strip()
        if line and not line.startswith("<!--"):
            return index
        index += 1
    return None


def _line_ranges(text: str) -> tuple[tuple[int, int, str], ...]:
    ranges: list[tuple[int, int, str]] = []
    start = 0
    for line in text.splitlines(keepends=True):
        end = start + len(line)
        ranges.append((start, end, line[:-1] if line.endswith("\n") else line))
        start = end
    return tuple(ranges)


def _symbol_directives(
    document: SourceDocument,
) -> tuple[tuple[SymbolDirective, ...], tuple[Diagnostic, ...]]:
    occupied = _code_spans(document)
    directives: list[SymbolDirective] = []
    diagnostics: list[Diagnostic] = []
    for match in SYMBOL_DIRECTIVE_RE.finditer(document.text):
        if _in_ranges(match.start(), occupied):
            continue
        directive, diagnostic = parse_symbol_directive(
            body=match.group("body"),
            raw=match.group(0),
            span=_span(document, match.start(), match.end()),
            source=SymbolDirectiveSource.MARKDOWN_COMMENT,
            make_span=lambda start, end: _span(document, start, end),
            body_start=match.start("body"),
        )
        if directive is not None:
            directives.append(directive)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return (
        tuple(sorted(directives, key=lambda directive: directive.span.start)),
        tuple(sorted(diagnostics, key=_diagnostic_key)),
    )


def _extract_role_target(body: str) -> str:
    angle = re.search(r"<([^<>]+)>\s*$", body)
    return angle.group(1).strip() if angle else body.strip()


def _normalize_label(value: str) -> str:
    value = value.strip()
    return value[1:] if value.startswith("#") else value


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


def _diagnostic_key(diagnostic: Diagnostic) -> int:
    return diagnostic.span.start if diagnostic.span is not None else 0
