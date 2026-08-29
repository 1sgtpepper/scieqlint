"""Fence, directive, code-cell, and structure-syntax lowering."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.structure import (
    CodeCellFact,
    DirectiveFact,
    FenceFact,
    StructureSyntaxIssueFact,
)
from scieqlint.io.source import SourceDocument
from scieqlint.markdown import is_escaped, is_fence_closer, parse_fence_opener
from scieqlint.source.maps import SourceMap

from .myst_shared import (
    CODE_CELL_TAG_RE,
    DIRECTIVE_INFO_RE,
    MYST_OPTION_RE,
    QUARTO_OPTION_RE,
    ROLE_MARKER_RE,
    ROLE_RE,
    LineRange,
    OffsetRange,
    extract_role_target_and_title,
    in_ranges,
    normalize_label,
)


def scan_fences(
    document: SourceDocument,
    smap: SourceMap,
    lines: Sequence[LineRange],
    live_ranges: Sequence[OffsetRange],
) -> tuple[FenceFact, ...]:
    live_starts = {start for start, _end in live_ranges}
    facts: list[FenceFact] = []
    index = 0
    while index < len(lines):
        start, end, line = lines[index]
        opener = parse_fence_opener(line)
        if opener is None or start not in live_starts:
            index += 1
            continue

        marker, info = opener
        close_index = _find_closing_fence(lines, index, marker)
        body_start = end
        body_end = lines[close_index][0] if close_index is not None else len(document.text)
        span_end = lines[close_index][1] if close_index is not None else body_end
        closer_span = (
            smap.span(lines[close_index][0], lines[close_index][1])
            if close_index is not None
            else None
        )
        facts.append(
            _make_fence_fact(
                document=document,
                smap=smap,
                start=start,
                end=span_end,
                body_start=body_start,
                body_end=body_end,
                marker=marker,
                info=info.strip(),
                is_closed=close_index is not None,
                opener_span=smap.span(start, end),
                closer_span=closer_span,
            )
        )
        index = close_index + 1 if close_index is not None else len(lines)
    return tuple(facts)


def directive_and_code_cell_facts(
    document: SourceDocument,
    fences: Sequence[FenceFact],
) -> tuple[tuple[DirectiveFact, ...], tuple[CodeCellFact, ...]]:
    directives: list[DirectiveFact] = []
    code_cells: list[CodeCellFact] = []
    for fence in fences:
        directive_match = DIRECTIVE_INFO_RE.match(fence.info_string)
        if directive_match is None:
            code_cell = _plain_code_cell_fact(document, fence)
            if code_cell is not None:
                code_cells.append(code_cell)
            continue

        directive = _directive_fact(fence, directive_match, myst_options(document, fence))
        directives.append(directive)
        code_cell = _directive_code_cell_fact(document, fence, directive, directive_match)
        if code_cell is not None:
            code_cells.append(code_cell)
    return tuple(directives), tuple(code_cells)


def scan_structure_syntax_issues(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
    fences: Sequence[FenceFact],
) -> Iterable[StructureSyntaxIssueFact]:
    yield from _malformed_directive_issues(fences)
    yield from _malformed_myst_option_issues(document, smap, fences)
    yield from _malformed_code_cell_tag_issues(document, smap, fences)
    yield from _malformed_role_issues(document, smap, occupied)


def _find_closing_fence(
    lines: Sequence[LineRange],
    opener_index: int,
    marker: str,
) -> int | None:
    for candidate_index in range(opener_index + 1, len(lines)):
        _start, _end, candidate_line = lines[candidate_index]
        if is_fence_closer(candidate_line, marker):
            return candidate_index
    return None


def _make_fence_fact(
    *,
    document: SourceDocument,
    smap: SourceMap,
    start: int,
    end: int,
    body_start: int,
    body_end: int,
    marker: str,
    info: str,
    is_closed: bool,
    opener_span: SourceSpan,
    closer_span: SourceSpan | None,
) -> FenceFact:
    directive = DIRECTIVE_INFO_RE.match(info)
    language = None
    kind = "generic"
    if info in {"math", "{math}"}:
        kind = "math"
    elif directive is not None:
        name = directive.group("name")
        kind = "code-cell" if name == "code-cell" else "directive"
        language = directive.group("arg").strip() or None
    elif info:
        language = info.split()[0]

    fact_id = f"{document.path.as_posix()}::fence::{start}"
    return FenceFact(
        fact_id=fact_id,
        document_id=document.path.as_posix(),
        span=smap.span(start, end),
        raw=document.text[start:end],
        opener=marker,
        fence_char=marker[0],
        fence_length=len(marker),
        info_string=info,
        language=language,
        kind=kind,
        is_closed=is_closed,
        opener_span=opener_span,
        closer_span=closer_span,
        body_span=smap.span(body_start, body_end) if body_end >= body_start else None,
    )


def _plain_code_cell_fact(document: SourceDocument, fence: FenceFact) -> CodeCellFact | None:
    if fence.language not in {"python", "r", "julia"}:
        return None
    options = quarto_options(document, fence)
    label = dict(options).get("label") or None
    normalized_label = normalize_label(label) if label is not None else None
    if not normalized_label:
        label = None
        normalized_label = None
    return CodeCellFact(
        fact_id=f"{fence.fact_id}::cell",
        document_id=fence.document_id,
        span=fence.span,
        raw=fence.raw,
        fence_fact_id=fence.fact_id,
        directive_fact_id=None,
        language=fence.language,
        engine=fence.language,
        options=options,
        label=label,
        normalized_label=normalized_label,
        label_span=(
            _option_value_span(document, fence, QUARTO_OPTION_RE, "label")
            if label is not None
            else None
        ),
    )


def _directive_fact(
    fence: FenceFact,
    directive_match: re.Match[str],
    options: tuple[tuple[str, str], ...],
) -> DirectiveFact:
    return DirectiveFact(
        fact_id=f"{fence.fact_id}::directive",
        document_id=fence.document_id,
        span=fence.opener_span,
        raw=fence.info_string,
        name=directive_match.group("name"),
        argument=directive_match.group("arg").strip() or None,
        options=options,
        fence_fact_id=fence.fact_id,
    )


def _directive_code_cell_fact(
    document: SourceDocument,
    fence: FenceFact,
    directive: DirectiveFact,
    directive_match: re.Match[str],
) -> CodeCellFact | None:
    name = directive_match.group("name")
    is_myst_code_cell = name == "code-cell"
    is_quarto_code_cell = name in {"python", "r", "julia", "bash"}
    if not (is_myst_code_cell or is_quarto_code_cell):
        return None

    options = directive.options if is_myst_code_cell else quarto_options(document, fence)
    option_map = dict(options)
    language = directive.argument if is_myst_code_cell else name
    tags = _parse_code_cell_tags(option_map.get("tags", ""))
    label_key = "label" if option_map.get("label") else "name"
    label = option_map.get(label_key) or None
    normalized_label = normalize_label(label) if label is not None else None
    if not normalized_label:
        label = None
        normalized_label = None
    return CodeCellFact(
        fact_id=f"{fence.fact_id}::cell",
        document_id=fence.document_id,
        span=fence.span,
        raw=fence.raw,
        fence_fact_id=fence.fact_id,
        directive_fact_id=directive.fact_id,
        language=language,
        engine=language,
        options=options,
        label=label,
        normalized_label=normalized_label,
        label_span=(
            _option_value_span(document, fence, MYST_OPTION_RE, label_key)
            if is_myst_code_cell and label is not None
            else _option_value_span(document, fence, QUARTO_OPTION_RE, label_key)
            if label is not None
            else None
        ),
        tags=tags,
    )


def _malformed_directive_issues(fences: Sequence[FenceFact]) -> Iterable[StructureSyntaxIssueFact]:
    for fence in fences:
        if not fence.info_string.startswith("{"):
            continue
        if DIRECTIVE_INFO_RE.match(fence.info_string) is not None:
            continue
        yield StructureSyntaxIssueFact(
            fact_id=f"{fence.fact_id}::syntax::directive",
            document_id=fence.document_id,
            span=fence.opener_span,
            raw=fence.info_string,
            kind="myst-directive",
            reason="malformed directive fence info string",
        )


def _malformed_myst_option_issues(
    document: SourceDocument,
    smap: SourceMap,
    fences: Sequence[FenceFact],
) -> Iterable[StructureSyntaxIssueFact]:
    for fence in fences:
        if DIRECTIVE_INFO_RE.match(fence.info_string) is None:
            continue
        for start, end, line in directive_option_prefix_lines(document, fence):
            if MYST_OPTION_RE.match(line) is not None:
                continue
            yield StructureSyntaxIssueFact(
                fact_id=f"{fence.fact_id}::syntax::option::{start}",
                document_id=fence.document_id,
                span=smap.span(start, end),
                raw=line,
                kind="myst-option",
                reason="malformed directive option line",
            )


def _malformed_code_cell_tag_issues(
    document: SourceDocument,
    smap: SourceMap,
    fences: Sequence[FenceFact],
) -> Iterable[StructureSyntaxIssueFact]:
    for fence in fences:
        directive_match = DIRECTIVE_INFO_RE.match(fence.info_string)
        if directive_match is None or directive_match.group("name") != "code-cell":
            continue
        for start, end, line in directive_option_prefix_lines(document, fence):
            match = MYST_OPTION_RE.match(line)
            if match is None or match.group("key") != "tags":
                continue
            if _code_cell_tags_error(match.group("value").strip()) is None:
                continue
            yield StructureSyntaxIssueFact(
                fact_id=f"{fence.fact_id}::syntax::tags::{start}",
                document_id=fence.document_id,
                span=smap.span(start, end),
                raw=line,
                kind="code-cell-tags",
                reason="malformed code-cell tags option",
            )


def _malformed_role_issues(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
) -> Iterable[StructureSyntaxIssueFact]:
    for match in ROLE_MARKER_RE.finditer(document.text):
        if in_ranges(match.start(), occupied) or is_escaped(document.text, match.start()):
            continue
        role_match = ROLE_RE.match(document.text, match.start())
        if role_match is not None:
            target, _title = extract_role_target_and_title(role_match.group("body"))
            if target:
                continue
        line_end = document.text.find("\n", match.start())
        if line_end == -1:
            line_end = len(document.text)
        yield StructureSyntaxIssueFact(
            fact_id=f"{document.path.as_posix()}::syntax::role::{match.start()}",
            document_id=document.path.as_posix(),
            span=smap.span(match.start(), line_end),
            raw=document.text[match.start() : line_end],
            kind="myst-role",
            reason="malformed MyST role syntax",
        )


def directive_option_prefix_lines(
    document: SourceDocument,
    fence: FenceFact,
) -> Iterable[LineRange]:
    if fence.body_span is None:
        return
    body_start = fence.body_span.start
    body = document.text[fence.body_span.start : fence.body_span.end]
    cursor = body_start
    for line in body.splitlines(keepends=True):
        end = cursor + len(line)
        line_without_newline = line[:-1] if line.endswith("\n") else line
        stripped = line_without_newline.strip()
        if not stripped:
            cursor = end
            continue
        if not stripped.startswith(":"):
            break
        yield (cursor, end, line_without_newline)
        if MYST_OPTION_RE.match(line_without_newline) is None:
            break
        cursor = end


def _parse_code_cell_tags(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    normalized = _strip_bracketed_tag_list(value) if value.startswith("[") else value
    if normalized is None:
        return ()
    tags = [_clean_tag(tag) for tag in normalized.split(",")]
    return tuple(tag for tag in tags if tag)


def _code_cell_tags_error(value: str) -> str | None:
    if not value:
        return None
    normalized = _strip_bracketed_tag_list(value) if value.startswith("[") else value
    if normalized is None:
        return "unclosed bracketed tag list"
    tags = [_clean_tag(tag) for tag in normalized.split(",")]
    if not tags or any(not tag for tag in tags):
        return "empty tag entry"
    if any(CODE_CELL_TAG_RE.fullmatch(tag) is None for tag in tags):
        return "tag contains unsupported characters"
    return None


def _strip_bracketed_tag_list(value: str) -> str | None:
    if not value.endswith("]"):
        return None
    return value[1:-1]


def _clean_tag(value: str) -> str:
    return value.strip().strip("\"'")


def _option_value_span(
    document: SourceDocument,
    fence: FenceFact,
    pattern: re.Pattern[str],
    key: str,
) -> SourceSpan | None:
    """Return the source span of the selected code-cell option value."""

    # ``scan_fences`` gives every emitted fence a body span, including empty
    # bodies.  Keep the value span anchored to the owning option rather than
    # widening a duplicate-target diagnostic to the whole cell.
    assert fence.body_span is not None
    body_span = fence.body_span
    body = document.text[body_span.start : body_span.end]
    offset = body_span.start
    selected: SourceSpan | None = None
    for line in body.splitlines(keepends=True):
        source_line = line.rstrip("\r\n")
        stripped = source_line.strip()
        if pattern is QUARTO_OPTION_RE and (
            not stripped or (stripped.startswith("#") and not stripped.startswith("#|"))
        ):
            offset += len(line)
            continue
        match = pattern.match(source_line)
        if match is None:
            if stripped:
                break
            offset += len(line)
            continue
        if match.group("key") == key:
            raw_value = match.group("value")
            leading = len(raw_value) - len(raw_value.lstrip())
            value = raw_value.strip()
            if not value:
                selected = None
            else:
                start = offset + match.start("value") + leading
                selected = SourceMap.for_document(document).span(start, start + len(value))
        offset += len(line)
    return selected


def myst_options(document: SourceDocument, fence: FenceFact) -> tuple[tuple[str, str], ...]:
    if fence.body_span is None:
        return ()
    body = document.text[fence.body_span.start : fence.body_span.end]
    options: list[tuple[str, str]] = []
    for line in body.splitlines():
        match = MYST_OPTION_RE.match(line)
        if match is not None:
            options.append((match.group("key"), match.group("value").strip()))
        elif line.strip():
            break
    return tuple(options)


def quarto_options(document: SourceDocument, fence: FenceFact) -> tuple[tuple[str, str], ...]:
    if fence.body_span is None:
        return ()
    body = document.text[fence.body_span.start : fence.body_span.end]
    return quarto_option_prefix(body)


def quarto_option_prefix(text: str) -> tuple[tuple[str, str], ...]:
    """Return Quarto options from the source preamble before executable code."""

    options: list[tuple[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or (stripped.startswith("#") and not stripped.startswith("#|")):
            continue
        match = QUARTO_OPTION_RE.match(line)
        if match is None:
            break
        options.append((match.group("key"), match.group("value").strip()))
    return tuple(options)
