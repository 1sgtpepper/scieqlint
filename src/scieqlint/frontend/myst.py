"""MyST/Markdown source lowering for structure, references, and math facts.

This is deliberately a conservative line-oriented frontend. It is not a full
replacement for MyST's parser. It produces facts with stable source spans;
semantic diagnostics remain owned by engines.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.facts.reference import (
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    TargetAnchorFact,
)
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import (
    CodeCellFact,
    DirectiveFact,
    FenceFact,
    HeadingFact,
    SectionFact,
    StructureSyntaxIssueFact,
)
from scieqlint.io.source import SourceDocument
from scieqlint.source.maps import SourceMap

_HEADING_RE = re.compile(r"^[ \t]{0,3}(?P<hashes>#{1,6})(?P<space>[ \t]+)?(?P<body>.*)$")
_ANCHOR_RE = re.compile(r"^[ \t]*\((?P<label>[^()\s]+)\)=[ \t]*$")
_FENCE_RE = re.compile(r"^(?P<indent>[ \t]{0,3})(?P<marker>`{3,}|~{3,})(?P<info>[^\n]*)$")
_MD_LINK_RE = re.compile(r"\[[^\]]*]\(#(?P<target>[^)\s]+)\)")
_ROLE_RE = re.compile(r"\{(?P<role>ref|eq|numref)}`(?P<body>[^`]+)`")
_INLINE_CODE_RE = re.compile(r"(?P<ticks>`+)[^`\n]*(?P=ticks)")
_INLINE_MATH_RE = re.compile(r"(?<!\$)\$(?!\$)(?P<body>[^\n$]+?)(?<!\$)\$(?!\$)")
_TEX_LABEL_RE = re.compile(r"\\label\{(?P<label>[^{}]+)\}")
_DOLLAR_TAIL_LABEL_RE = re.compile(r"\{#(?P<brace>[^}\s]+)\}|\((?P<paren>[^()\s]+)\)")
_DIRECTIVE_INFO_RE = re.compile(r"^\{(?P<name>[^}\s]+)\}(?P<arg>.*)$")
_ROLE_MARKER_RE = re.compile(r"\{(?P<role>ref|eq|numref)\}")
_QUARTO_OPTION_RE = re.compile(r"^[ \t]*#\|[ \t]*(?P<key>[A-Za-z0-9_.-]+):[ \t]*(?P<value>.*)$")
_MYST_OPTION_RE = re.compile(
    r"^[ \t]*:(?P<key>[A-Za-z0-9_.-]+):[ \t]*(?P<value>.*)$",
    re.MULTILINE,
)
_CODE_CELL_TAG_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

LineRange = tuple[int, int, str]
OffsetRange = tuple[int, int]


class MySTFrontend:
    """Lower source documents into a ``FactSnapshot`` without diagnostics."""

    def lower(self, documents: Sequence[SourceDocument]) -> FactSnapshot:
        parts = tuple(_lower_document(document) for document in documents)
        return FactSnapshot(
            documents=tuple(documents),
            headings=_flatten(parts, "headings"),
            sections=_flatten(parts, "sections"),
            fences=_flatten(parts, "fences"),
            directives=_flatten(parts, "directives"),
            code_cells=_flatten(parts, "code_cells"),
            structure_syntax_issues=_flatten(parts, "structure_syntax_issues"),
            target_anchors=_flatten(parts, "target_anchors"),
            generic_refs=_flatten(parts, "generic_refs"),
            equation_labels=_flatten(parts, "equation_labels"),
            equation_refs=_flatten(parts, "equation_refs"),
            inline_math=_flatten(parts, "inline_math"),
            display_math=_flatten(parts, "display_math"),
        )


def _flatten(parts: Sequence[FactSnapshot], name: str) -> tuple[Any, ...]:
    items: list[Any] = []
    for part in parts:
        items.extend(getattr(part, name))
    return tuple(items)


def _lower_document(document: SourceDocument) -> FactSnapshot:
    smap = SourceMap.for_document(document)
    lines = _line_ranges(document.text)
    fences = _scan_fences(document, smap, lines)
    fence_ranges = _fence_ranges(fences, document.text)
    directives, code_cells = _directive_and_code_cell_facts(document, fences)
    structure_syntax_issues = tuple(
        _scan_structure_syntax_issues(document, smap, fence_ranges, fences)
    )
    headings = tuple(_scan_headings(document, smap, lines, fence_ranges))
    anchors = tuple(_scan_anchors(document, smap, lines, fence_ranges))
    target_anchors = tuple(_attach_anchors(document, anchors, headings, fences))
    sections = tuple(_sections_for_headings(headings))
    display_math, equation_labels = _scan_display_math(document, smap, fence_ranges, fences)
    generic_refs, equation_refs = _scan_refs(document, smap, fence_ranges)
    inline_math = tuple(
        _scan_inline_math(document, smap, _math_occupied_ranges(fence_ranges, display_math))
    )
    return FactSnapshot(
        documents=(document,),
        headings=headings,
        sections=sections,
        fences=fences,
        directives=directives,
        code_cells=code_cells,
        structure_syntax_issues=structure_syntax_issues,
        target_anchors=target_anchors,
        generic_refs=generic_refs,
        equation_labels=equation_labels,
        equation_refs=equation_refs,
        inline_math=inline_math,
        display_math=display_math,
    )


def _line_ranges(text: str) -> tuple[LineRange, ...]:
    ranges: list[LineRange] = []
    start = 0
    for line in text.splitlines(keepends=True):
        end = start + len(line)
        ranges.append((start, end, line[:-1] if line.endswith("\n") else line))
        start = end
    return tuple(ranges)


def _fence_ranges(fences: Sequence[FenceFact], text: str) -> tuple[OffsetRange, ...]:
    return tuple(
        (
            fence.opener_span.start,
            fence.closer_span.end if fence.closer_span is not None else len(text),
        )
        for fence in fences
    )


def _math_occupied_ranges(
    fence_ranges: Sequence[OffsetRange],
    display_math: Sequence[DisplayMathFact],
) -> tuple[OffsetRange, ...]:
    math_ranges = tuple(
        (fact.span.start, fact.span.end) for fact in display_math if fact.span is not None
    )
    return (*tuple(fence_ranges), *math_ranges)


def _scan_fences(
    document: SourceDocument,
    smap: SourceMap,
    lines: Sequence[LineRange],
) -> tuple[FenceFact, ...]:
    facts: list[FenceFact] = []
    index = 0
    while index < len(lines):
        start, end, line = lines[index]
        match = _FENCE_RE.match(line)
        if not match:
            index += 1
            continue

        marker = match.group("marker")
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
                info=match.group("info").strip(),
                is_closed=close_index is not None,
                opener_span=smap.span(start, end),
                closer_span=closer_span,
            )
        )
        index = close_index + 1 if close_index is not None else len(lines)
    return tuple(facts)


def _find_closing_fence(
    lines: Sequence[LineRange],
    opener_index: int,
    marker: str,
) -> int | None:
    fence_char = marker[0]
    fence_len = len(marker)
    for candidate_index in range(opener_index + 1, len(lines)):
        _start, _end, candidate_line = lines[candidate_index]
        stripped = candidate_line.strip()
        if stripped.startswith(fence_char * fence_len) and set(stripped) <= {fence_char}:
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
    directive = _DIRECTIVE_INFO_RE.match(info)
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


def _directive_and_code_cell_facts(
    document: SourceDocument,
    fences: Sequence[FenceFact],
) -> tuple[tuple[DirectiveFact, ...], tuple[CodeCellFact, ...]]:
    directives: list[DirectiveFact] = []
    code_cells: list[CodeCellFact] = []
    for fence in fences:
        directive_match = _DIRECTIVE_INFO_RE.match(fence.info_string)
        if directive_match is None:
            code_cell = _plain_code_cell_fact(document, fence)
            if code_cell is not None:
                code_cells.append(code_cell)
            continue

        directive = _directive_fact(fence, directive_match, _myst_options(document, fence))
        directives.append(directive)
        code_cell = _directive_code_cell_fact(document, fence, directive, directive_match)
        if code_cell is not None:
            code_cells.append(code_cell)
    return tuple(directives), tuple(code_cells)


def _plain_code_cell_fact(document: SourceDocument, fence: FenceFact) -> CodeCellFact | None:
    if fence.language not in {"python", "r", "julia"}:
        return None
    options = _quarto_options(document, fence)
    label = dict(options).get("label")
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

    options = directive.options if is_myst_code_cell else _quarto_options(document, fence)
    option_map = dict(options)
    language = directive.argument if is_myst_code_cell else name
    tags = _parse_code_cell_tags(option_map.get("tags", ""))
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
        label=option_map.get("label") or option_map.get("name"),
        tags=tags,
    )


def _scan_structure_syntax_issues(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
    fences: Sequence[FenceFact],
) -> Iterable[StructureSyntaxIssueFact]:
    yield from _malformed_directive_issues(fences)
    yield from _malformed_myst_option_issues(document, smap, fences)
    yield from _malformed_code_cell_tag_issues(document, smap, fences)
    yield from _malformed_role_issues(document, smap, occupied)


def _malformed_directive_issues(fences: Sequence[FenceFact]) -> Iterable[StructureSyntaxIssueFact]:
    for fence in fences:
        if not fence.info_string.startswith("{"):
            continue
        if _DIRECTIVE_INFO_RE.match(fence.info_string) is not None:
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
        if _DIRECTIVE_INFO_RE.match(fence.info_string) is None:
            continue
        for start, end, line in _directive_option_prefix_lines(document, fence):
            if _MYST_OPTION_RE.match(line) is not None:
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
        directive_match = _DIRECTIVE_INFO_RE.match(fence.info_string)
        if directive_match is None or directive_match.group("name") != "code-cell":
            continue
        for start, end, line in _directive_option_prefix_lines(document, fence):
            match = _MYST_OPTION_RE.match(line)
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
    occupied_with_code = (*tuple(occupied), *_inline_code_ranges(document))
    for match in _ROLE_MARKER_RE.finditer(document.text):
        if _in_ranges(match.start(), occupied_with_code):
            continue
        if _ROLE_RE.match(document.text, match.start()) is not None:
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


def _directive_option_prefix_lines(
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
    if any(_CODE_CELL_TAG_RE.fullmatch(tag) is None for tag in tags):
        return "tag contains unsupported characters"
    return None


def _strip_bracketed_tag_list(value: str) -> str | None:
    if not value.endswith("]"):
        return None
    return value[1:-1]


def _clean_tag(value: str) -> str:
    return value.strip().strip("\"'")


def _myst_options(document: SourceDocument, fence: FenceFact) -> tuple[tuple[str, str], ...]:
    if fence.body_span is None:
        return ()
    body = document.text[fence.body_span.start : fence.body_span.end]
    options: list[tuple[str, str]] = []
    for line in body.splitlines():
        match = _MYST_OPTION_RE.match(line)
        if match is not None:
            options.append((match.group("key"), match.group("value").strip()))
        elif line.strip():
            break
    return tuple(options)


def _quarto_options(document: SourceDocument, fence: FenceFact) -> tuple[tuple[str, str], ...]:
    if fence.body_span is None:
        return ()
    body = document.text[fence.body_span.start : fence.body_span.end]
    options: list[tuple[str, str]] = []
    for line in body.splitlines():
        match = _QUARTO_OPTION_RE.match(line)
        if match is not None:
            options.append((match.group("key"), match.group("value").strip()))
    return tuple(options)


def _scan_headings(
    document: SourceDocument,
    smap: SourceMap,
    lines: Sequence[LineRange],
    occupied: Sequence[OffsetRange],
) -> Iterable[HeadingFact]:
    for start, end, line in lines:
        if _in_ranges(start, occupied):
            continue
        match = _HEADING_RE.match(line)
        if match is None:
            continue

        hashes = match.group("hashes")
        body = match.group("body")
        text = _heading_text(body)
        if not text:
            continue

        indent = len(line) - len(line.lstrip(" \t"))
        space = match.group("space")
        text_start = start + indent + len(hashes) + (len(space) if space else 0)
        yield HeadingFact(
            fact_id=f"{document.path.as_posix()}::heading::{start}",
            document_id=document.path.as_posix(),
            span=smap.span(start, end),
            raw=line,
            level=len(hashes),
            text=text,
            slug_candidate=_slug(text),
            marker_span=smap.span(start + indent, start + indent + len(hashes)),
            text_span=smap.span(text_start, text_start + len(body.lstrip())) if body else None,
            valid_atx=space is not None,
            malformation=None if space is not None else "missing_space_after_atx_marker",
        )


def _heading_text(body: str) -> str:
    stripped = body.strip()
    return re.sub(r"[ \t]+#+[ \t]*$", "", stripped).strip()


def _scan_anchors(
    document: SourceDocument,
    smap: SourceMap,
    lines: Sequence[LineRange],
    occupied: Sequence[OffsetRange],
) -> Iterable[TargetAnchorFact]:
    for start, end, line in lines:
        if _in_ranges(start, occupied):
            continue
        match = _ANCHOR_RE.match(line)
        if match is None:
            continue
        label = match.group("label")
        label_start = start + match.start("label")
        yield TargetAnchorFact(
            fact_id=f"{document.path.as_posix()}::anchor::{start}",
            document_id=document.path.as_posix(),
            span=smap.span(start, end),
            raw=line,
            label=label,
            normalized_label=_normalize(label),
            target_kind=None,
            attaches_to_fact_id=None,
            placement="standalone",
            label_span=smap.span(label_start, label_start + len(label)),
        )


def _attach_anchors(
    document: SourceDocument,
    anchors: Iterable[TargetAnchorFact],
    headings: Sequence[HeadingFact],
    fences: Sequence[FenceFact],
) -> Iterable[TargetAnchorFact]:
    attachable = sorted((*headings, *fences), key=lambda fact: fact.span.start if fact.span else 0)
    for anchor in anchors:
        next_fact = next(
            (
                fact
                for fact in attachable
                if fact.span is not None
                and anchor.span is not None
                and fact.span.start >= anchor.span.end
            ),
            None,
        )
        if next_fact is None or not _is_immediate_attachment(document, anchor, next_fact):
            yield replace(anchor, placement="orphaned")
            continue
        kind = "heading" if isinstance(next_fact, HeadingFact) else "block"
        placement = "before_heading" if kind == "heading" else "before_block"
        yield replace(
            anchor,
            target_kind=kind,
            attaches_to_fact_id=next_fact.fact_id,
            placement=placement,
        )


def _is_immediate_attachment(
    document: SourceDocument,
    anchor: TargetAnchorFact,
    next_fact: HeadingFact | FenceFact,
) -> bool:
    if anchor.span is None or next_fact.span is None:
        return False
    between = document.text[anchor.span.end : next_fact.span.start]
    for line in between.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("<!--"):
            return False
    return True


def _sections_for_headings(headings: Sequence[HeadingFact]) -> Iterable[SectionFact]:
    stack: list[tuple[int, str]] = []
    counters = [0] * 7
    for heading in headings:
        level = heading.level
        counters[level] += 1
        for idx in range(level + 1, 7):
            counters[idx] = 0
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else None
        fact_id = f"{heading.fact_id}::section"
        stack.append((level, fact_id))
        yield SectionFact(
            fact_id=fact_id,
            document_id=heading.document_id,
            span=heading.span,
            raw=heading.raw,
            heading_fact_id=heading.fact_id,
            parent_section_id=parent,
            depth=level,
            ordinal_path=tuple(counters[1 : level + 1]),
            starts_at=heading.span,
        )


def _scan_display_math(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
    fences: Sequence[FenceFact],
) -> tuple[tuple[DisplayMathFact, ...], tuple[EquationLabelFact, ...]]:
    display: list[DisplayMathFact] = []
    labels: list[EquationLabelFact] = []
    for fence in fences:
        if fence.kind != "math" or fence.body_span is None:
            continue
        math_fact, label_facts = _math_fact_from_fence(document, smap, fence)
        display.append(math_fact)
        labels.extend(label_facts)

    dollar_display, dollar_labels = _dollar_display_math(document, smap, occupied)
    display.extend(dollar_display)
    labels.extend(dollar_labels)
    return tuple(display), tuple(labels)


def _math_fact_from_fence(
    document: SourceDocument,
    smap: SourceMap,
    fence: FenceFact,
) -> tuple[DisplayMathFact, tuple[EquationLabelFact, ...]]:
    assert fence.body_span is not None
    body_text = document.text[fence.body_span.start : fence.body_span.end]
    body = body_text.strip()
    fact_id = f"{fence.fact_id}::math"
    labels = list(_tex_label_facts(document, smap, fact_id, fence.body_span.start, body_text))
    if fence.info_string == "{math}":
        labels.extend(_myst_math_label_facts(document, smap, fact_id, fence))
    return (
        DisplayMathFact(
            fact_id=fact_id,
            document_id=fence.document_id,
            span=fence.body_span,
            raw=body,
            body=body,
            container="myst-math-directive" if fence.info_string == "{math}" else "fenced-math",
            label_fact_ids=tuple(label.fact_id for label in labels),
        ),
        tuple(labels),
    )


def _dollar_display_math(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
) -> tuple[tuple[DisplayMathFact, ...], tuple[EquationLabelFact, ...]]:
    display: list[DisplayMathFact] = []
    labels: list[EquationLabelFact] = []
    cursor = 0
    while True:
        start = document.text.find("$$", cursor)
        if start == -1:
            break
        if _in_ranges(start, occupied):
            cursor = start + 2
            continue
        close = _find_unoccupied_display_close(document.text, start + 2, occupied)
        if close == -1:
            cursor = start + 2
            continue
        fact_id = f"{document.path.as_posix()}::display-math::{start}"
        body_start = start + 2
        body_end = close
        body_text = document.text[body_start:body_end]
        label_facts = list(_tex_label_facts(document, smap, fact_id, body_start, body_text))
        label_facts.extend(_dollar_tail_label_facts(document, smap, fact_id, close))
        labels.extend(label_facts)
        display.append(
            DisplayMathFact(
                fact_id=fact_id,
                document_id=document.path.as_posix(),
                span=smap.span(body_start, body_end),
                raw=body_text.strip(),
                body=body_text.strip(),
                container="dollar-dollar",
                label_fact_ids=tuple(label.fact_id for label in label_facts),
            )
        )
        cursor = close + 2
    return tuple(display), tuple(labels)


def _find_unoccupied_display_close(
    text: str,
    start: int,
    occupied: Sequence[OffsetRange],
) -> int:
    cursor = start
    while True:
        close = text.find("$$", cursor)
        if close == -1:
            return -1
        if not _in_ranges(close, occupied):
            return close
        cursor = close + 2


def _tex_label_facts(
    document: SourceDocument,
    smap: SourceMap,
    fact_id: str,
    body_start: int,
    body_text: str,
) -> Iterable[EquationLabelFact]:
    for match in _TEX_LABEL_RE.finditer(body_text):
        label = match.group("label")
        label_start = body_start + match.start("label")
        yield EquationLabelFact(
            fact_id=f"{fact_id}::label::{label_start}",
            document_id=document.path.as_posix(),
            span=smap.span(label_start, label_start + len(label)),
            raw=label,
            label=label,
            normalized_label=_normalize(label),
            label_syntax_kind="tex-label",
            source_block_id=fact_id,
            label_span=smap.span(label_start, label_start + len(label)),
        )


def _myst_math_label_facts(
    document: SourceDocument,
    smap: SourceMap,
    fact_id: str,
    fence: FenceFact,
) -> Iterable[EquationLabelFact]:
    assert fence.body_span is not None
    body_text = document.text[fence.body_span.start : fence.body_span.end]
    for match in _MYST_OPTION_RE.finditer(body_text):
        if match.group("key") != "label":
            continue
        label = match.group("value").strip()
        label_start = fence.body_span.start + match.start("value")
        yield EquationLabelFact(
            fact_id=f"{fact_id}::label::{label_start}",
            document_id=document.path.as_posix(),
            span=smap.span(label_start, label_start + len(label)),
            raw=label,
            label=label,
            normalized_label=_normalize(label),
            label_syntax_kind="myst-directive-option",
            source_block_id=fact_id,
            label_span=smap.span(label_start, label_start + len(label)),
        )


def _dollar_tail_label_facts(
    document: SourceDocument,
    smap: SourceMap,
    fact_id: str,
    close: int,
) -> Iterable[EquationLabelFact]:
    line_end = document.text.find("\n", close)
    if line_end == -1:
        line_end = len(document.text)
    tail_start = close + 2
    tail = document.text[tail_start:line_end]
    for match in _DOLLAR_TAIL_LABEL_RE.finditer(tail):
        group_name = "brace" if match.group("brace") else "paren"
        label = match.group(group_name)
        assert label is not None
        label_start = tail_start + match.start(group_name)
        yield EquationLabelFact(
            fact_id=f"{fact_id}::label::{label_start}",
            document_id=document.path.as_posix(),
            span=smap.span(label_start, label_start + len(label)),
            raw=label,
            label=label,
            normalized_label=_normalize(label),
            label_syntax_kind="dollar-tail",
            source_block_id=fact_id,
            label_span=smap.span(label_start, label_start + len(label)),
        )


def _scan_refs(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
) -> tuple[tuple[GenericRefFact, ...], tuple[EquationRefFact, ...]]:
    generic: list[GenericRefFact] = []
    equation: list[EquationRefFact] = []
    occupied_with_code = (*tuple(occupied), *_inline_code_ranges(document))
    for match in _MD_LINK_RE.finditer(document.text):
        if _in_ranges(match.start(), occupied_with_code):
            continue
        generic.append(_markdown_link_ref_fact(document, smap, match))
    for match in _ROLE_RE.finditer(document.text):
        if _in_ranges(match.start(), occupied_with_code):
            continue
        role = match.group("role")
        body = match.group("body")
        target, title = _extract_role_target_and_title(body)
        target_start = match.start("body") + body.rfind(target)
        if role == "ref":
            generic.append(
                _generic_role_ref_fact(document, smap, match, target, title, target_start)
            )
        else:
            equation.append(
                _equation_role_ref_fact(document, smap, match, role, target, target_start)
            )
    return tuple(generic), tuple(equation)


def _markdown_link_ref_fact(
    document: SourceDocument,
    smap: SourceMap,
    match: re.Match[str],
) -> GenericRefFact:
    target = match.group("target")
    return GenericRefFact(
        fact_id=f"{document.path.as_posix()}::md-ref::{match.start('target')}",
        document_id=document.path.as_posix(),
        span=smap.span(match.start(), match.end()),
        raw=match.group(0),
        role_kind="markdown-link",
        target=target,
        normalized_target=_normalize(target),
        role_span=smap.span(match.start(), match.end()),
        target_span=smap.span(match.start("target"), match.end("target")),
    )


def _generic_role_ref_fact(
    document: SourceDocument,
    smap: SourceMap,
    match: re.Match[str],
    target: str,
    title: str | None,
    target_start: int,
) -> GenericRefFact:
    return GenericRefFact(
        fact_id=f"{document.path.as_posix()}::ref::{target_start}",
        document_id=document.path.as_posix(),
        span=smap.span(match.start(), match.end()),
        raw=match.group(0),
        role_kind="ref",
        target=target,
        normalized_target=_normalize(target),
        title=title,
        role_span=smap.span(match.start(), match.end()),
        target_span=smap.span(target_start, target_start + len(target)),
    )


def _equation_role_ref_fact(
    document: SourceDocument,
    smap: SourceMap,
    match: re.Match[str],
    role: str,
    target: str,
    target_start: int,
) -> EquationRefFact:
    return EquationRefFact(
        fact_id=f"{document.path.as_posix()}::eq-ref::{target_start}",
        document_id=document.path.as_posix(),
        span=smap.span(match.start(), match.end()),
        raw=match.group(0),
        ref_kind=role,
        target=target,
        normalized_target=_normalize(target),
        role_span=smap.span(match.start(), match.end()),
        target_span=smap.span(target_start, target_start + len(target)),
    )


def _scan_inline_math(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
) -> Iterable[InlineMathFact]:
    occupied_with_code = (*tuple(occupied), *_inline_code_ranges(document))
    for match in _INLINE_MATH_RE.finditer(document.text):
        if _in_ranges(match.start(), occupied_with_code):
            continue
        body = match.group("body")
        yield InlineMathFact(
            fact_id=f"{document.path.as_posix()}::inline-math::{match.start()}",
            document_id=document.path.as_posix(),
            span=smap.span(match.start("body"), match.end("body")),
            raw=match.group(0),
            body=body,
            delimiter_kind="dollar",
            context="paragraph",
        )


def _inline_code_ranges(document: SourceDocument) -> tuple[OffsetRange, ...]:
    return tuple((match.start(), match.end()) for match in _INLINE_CODE_RE.finditer(document.text))


def _in_ranges(position: int, ranges: Sequence[OffsetRange]) -> bool:
    return any(start <= position < end for start, end in ranges)


def _extract_role_target_and_title(body: str) -> tuple[str, str | None]:
    angle = re.search(r"<([^<>]+)>\s*$", body)
    if angle is not None:
        title = body[: angle.start()].strip() or None
        return angle.group(1).strip(), title
    return body.strip(), None


def _normalize(value: str) -> str:
    value = value.strip()
    if value.startswith("#"):
        value = value[1:]
    return value


def _slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9 _.-]+", "", text).strip().lower()
    return re.sub(r"[\s_]+", "-", slug)
