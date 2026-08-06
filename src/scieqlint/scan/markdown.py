"""Markdown and MyST scanner for the v0.1 subset."""

from __future__ import annotations

import re
from collections.abc import Iterable

from scieqlint.config.model import Config
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.io.source import SourceDocument
from scieqlint.markdown import (
    code_fence_ranges,
    dollar_display_opener_positions,
    dollar_display_ranges,
    dollar_inline_ranges,
    inline_code_ranges,
    is_escaped,
    is_fence_closer,
)
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

TEX_LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")
DOLLAR_LABEL_RE = re.compile(r"\{#([^}\s]+)\}|\(([^()\s]+)\)")
MYST_LABEL_RE = re.compile(r"^[ \t]*:label:[ \t]*(?P<label>\S+)[ \t]*$", re.MULTILINE)
MYST_ANCHOR_RE = re.compile(r"^[ \t]*\((?P<label>[^()\s]+)\)=[ \t]*$")
HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}(?!#)[ \t]+\S")
MD_LINK_RE = re.compile(r"\[[^\]]*]\(#(?P<target>[^)\s]+)\)")
EQ_ROLE_RE = re.compile(r"\{(?P<role>eq|numref)\}`(?P<body>[^`]+)`")
LINK_METADATA_RE = re.compile(
    r"(?P<image>!?)(?:\[(?P<label>(?:\\.|[^]\n])*)\]\((?P<body>[^)\n]*)\))"
)
SYMBOL_DIRECTIVE_RE = re.compile(
    r"<!--\s*scieqlint-symbol:\s*(?P<body>.*?)\s*-->",
    re.DOTALL,
)

_MathFenceRange = tuple[int, int, int, int | None]


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
            math_fences = _math_fence_ranges(document.text)
            for block in _fenced_blocks(document, math_fences):
                blocks.append(block)
                labels.extend(_tex_labels(document, block))
                labels.extend(_myst_directive_labels(document, block))
            diagnostics.extend(_unterminated_fence_diagnostics(document, math_fences))

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
        span_start, span_end = _trimmed_body_range(document, body_start, body_end)
        text = document.text[span_start:span_end]
        if not text:
            continue
        span = _span(document, span_start, span_end)
        yield MathBlock(
            text=text,
            source_aligned_text=text,
            span=span,
            block_id=_block_id(document, span, MathContainer.MARKDOWN_DISPLAY),
            container=MathContainer.MARKDOWN_DISPLAY,
        )


def _unterminated_display_diagnostics(document: SourceDocument) -> Iterable[Diagnostic]:
    # Both lexical results identify a display opener by its exact source start.
    closed_starts = {start for start, _body_start, _body_end, _end in _display_ranges(document)}
    for start in dollar_display_opener_positions(document.text, ()):
        if start in closed_starts:
            continue
        yield _scan_diagnostic(document, start, start + 2)


def _display_ranges(document: SourceDocument) -> Iterable[tuple[int, int, int, int]]:
    return iter(dollar_display_ranges(document.text, ()))


def _inline_ranges(
    document: SourceDocument,
    occupied: tuple[tuple[int, int], ...],
) -> Iterable[tuple[int, int, int, int]]:
    return iter(dollar_inline_ranges(document.text, occupied))


def _math_fence_ranges(text: str) -> tuple[_MathFenceRange, ...]:
    """Derive supported math fences from the shared lexical ownership result."""
    ranges: list[_MathFenceRange] = []
    for opener_start, range_end in code_fence_ranges(text):
        source = text[opener_start:range_end]
        opener_line, newline, _body = source.partition("\n")
        if opener_line.removeprefix("```").rstrip(" \t") not in {"math", "{math}"}:
            continue
        marker = "```"
        opener_end = opener_start + len(opener_line)
        body_start = opener_end + len(newline)
        lines = source.splitlines(keepends=True)
        body_end = range_end - len(lines[-1]) if is_fence_closer(lines[-1], marker) else None
        ranges.append((opener_start, opener_end, body_start, body_end))
    return tuple(ranges)


def _fenced_blocks(
    document: SourceDocument,
    fences: Iterable[_MathFenceRange],
) -> Iterable[MathBlock]:
    for _opener_start, _opener_end, body_start, body_end in fences:
        if body_end is None:
            continue
        span_start, span_end = _trimmed_body_range(document, body_start, body_end)
        span = _span(document, span_start, span_end)
        text = document.text[span_start:span_end]
        yield MathBlock(
            text=text,
            source_aligned_text=text,
            span=span,
            block_id=_block_id(document, span, MathContainer.MARKDOWN_FENCE),
            container=MathContainer.MARKDOWN_FENCE,
        )


def math_container_opener_lines(
    document: SourceDocument,
    blocks: Iterable[MathBlock],
) -> dict[str, int]:
    block_ids = {
        (block.container, block.span.start, block.span.end): block.block_id for block in blocks
    }
    opener_lines: dict[str, int] = {}
    for opener_start, body_start, body_end, _end in _display_ranges(document):
        span_start, span_end = _trimmed_body_range(document, body_start, body_end)
        block_id = block_ids.get((MathContainer.MARKDOWN_DISPLAY, span_start, span_end))
        if block_id is not None:
            opener_lines[block_id] = document.line_index.position(opener_start)[0]
    for opener_start, _opener_end, body_start, body_end in _math_fence_ranges(document.text):
        if body_end is None:
            continue
        span_start, span_end = _trimmed_body_range(document, body_start, body_end)
        block_id = block_ids.get((MathContainer.MARKDOWN_FENCE, span_start, span_end))
        if block_id is not None:
            opener_lines[block_id] = document.line_index.position(opener_start)[0]
    return opener_lines


def _trimmed_body_range(
    document: SourceDocument,
    body_start: int,
    body_end: int,
) -> tuple[int, int]:
    body = document.text[body_start:body_end]
    return (
        body_start + len(body) - len(body.lstrip()),
        body_start + len(body.rstrip()),
    )


def _unterminated_fence_diagnostics(
    document: SourceDocument,
    fences: Iterable[_MathFenceRange],
) -> Iterable[Diagnostic]:
    for opener_start, opener_end, _body_start, body_end in fences:
        if body_end is None:
            yield _scan_diagnostic(document, opener_start, opener_end)


def _inline_blocks(
    document: SourceDocument,
    existing_blocks: list[MathBlock],
) -> Iterable[MathBlock]:
    occupied = tuple((block.span.start, block.span.end) for block in existing_blocks)
    for _start, body_start, body_end, _end in _inline_ranges(document, occupied):
        body = document.text[body_start:body_end]
        text = body.strip()
        if not text:
            continue
        span_start = body_start + len(body) - len(body.lstrip())
        span_end = body_start + len(body.rstrip())
        span = _span(document, span_start, span_end)
        yield MathBlock(
            text=text,
            source_aligned_text=text,
            span=span,
            block_id=_block_id(document, span, MathContainer.MARKDOWN_INLINE),
            container=MathContainer.MARKDOWN_INLINE,
        )


def _code_spans(document: SourceDocument) -> tuple[tuple[int, int], ...]:
    return (
        *inline_code_ranges(document.text),
        *code_fence_ranges(document.text),
    )


def _in_ranges(position: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= position < end for start, end in ranges)


def _tex_labels(document: SourceDocument, block: MathBlock) -> Iterable[EquationLabel]:
    for match in TEX_LABEL_RE.finditer(block.text):
        if is_escaped(block.text, match.start()):
            continue
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
    leading = len(tail) - len(tail.lstrip(" \t"))
    trailing = len(tail.rstrip(" \t"))
    candidate = tail[leading:trailing]
    match = DOLLAR_LABEL_RE.fullmatch(candidate)
    if match is None:
        return
    group_name = 1 if match.group(1) else 2
    raw = match.group(group_name)
    assert raw is not None
    label_start = tail_start + leading + match.start(group_name)
    label_end = tail_start + leading + match.end(group_name)
    yield EquationLabel(
        label=_normalize_label(raw),
        span=_span(document, label_start, label_end),
        block_id=block.block_id,
        source=(LabelSource.MYST_DOLLAR_LABEL if match.group(2) else LabelSource.MARKDOWN_ANCHOR),
    )


def _myst_directive_labels(document: SourceDocument, block: MathBlock) -> Iterable[EquationLabel]:
    offset = 0
    for line in block.text.splitlines(keepends=True):
        line_without_newline = line[:-1] if line.endswith("\n") else line
        if not line_without_newline.strip():
            offset += len(line)
            continue
        if not line_without_newline.lstrip().startswith(":"):
            break
        match = MYST_LABEL_RE.fullmatch(line_without_newline)
        if match is None:
            break
        label_start = block.span.start + offset + match.start("label")
        label_end = block.span.start + offset + match.end("label")
        yield EquationLabel(
            label=_normalize_label(match.group("label")),
            span=_span(document, label_start, label_end),
            block_id=block.block_id,
            source=LabelSource.MYST_DIRECTIVE_LABEL,
        )
        offset += len(line)


def _references(document: SourceDocument) -> Iterable[EquationReference]:
    attached_myst_anchors = _attached_myst_heading_anchor_targets(document)
    link_metadata = _link_metadata_ranges(document.text)
    for match in MD_LINK_RE.finditer(document.text):
        if (
            _in_ranges(match.start(), link_metadata)
            or _is_escaped(document.text, match.start())
            or (match.start() > 0 and document.text[match.start() - 1] == "!")
        ):
            continue
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
        if _in_ranges(match.start(), link_metadata) or _is_escaped(
            document.text, match.start()
        ):
            continue
        role = match.group("role")
        body = match.group("body")
        target = _extract_role_target(body)
        if not target:
            continue
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


def _link_metadata_ranges(text: str) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    for match in LINK_METADATA_RE.finditer(text):
        if match.group("image"):
            ranges.append((match.start(), match.end()))
        else:
            ranges.append((match.start("body"), match.end()))
    return tuple(ranges)


def _is_escaped(text: str, index: int) -> bool:
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return slash_count % 2 == 1


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
