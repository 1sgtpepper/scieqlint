"""Shared ordered lexical intervals for Markdown code, math, links, and opacity."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from html import unescape
from html.entities import html5
from itertools import chain

OffsetRange = tuple[int, int]
DollarRange = tuple[int, int, int, int]

HTML_COMMENT_RE = re.compile(r"<!--.*?(?:-->|$)", re.DOTALL)
HTML_DECLARATION_RE = re.compile(r"<![A-Z][^>]*?(?:>|$)", re.IGNORECASE | re.DOTALL)
HTML_PROCESSING_INSTRUCTION_RE = re.compile(r"<\?.*?(?:\?>|$)", re.DOTALL)
HTML_CDATA_RE = re.compile(r"<!\[CDATA\[.*?(?:\]\]>|$)", re.DOTALL)
HTML_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9:-]*(?:\s+[^<>]*?)?/?>", re.IGNORECASE)
HTML_TAG_EVENT_RE = re.compile(
    r"<(?P<closing>/[ \t]*)?(?P<tag>[A-Za-z][A-Za-z0-9:-]*)(?=[ \t/>])"
    r"(?P<tail>[^<>]*)>",
    re.IGNORECASE,
)
HTML_BLOCK_OPEN_RE = re.compile(
    r"^[ \t]{0,3}<(?P<tag>address|article|aside|base|basefont|blockquote|body|caption|"
    r"center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|"
    r"footer|form|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|"
    r"nav|ol|p|pre|script|section|summary|table|tbody|td|tfoot|th|thead|title|tr|"
    r"track|ul)(?:[ \t/>]|$)",
    re.IGNORECASE | re.MULTILINE,
)
HTML_RAWTEXT_TAGS = frozenset({"script", "style", "textarea", "title"})
_MYST_ROLE_RE = re.compile(r"\{(?:ref|eq|numref)\}`[^`\r\n]+`")
_MARKDOWN_ANCHOR_RE = re.compile(r"^[ \t]*\((?P<label>[^()\s]+)\)=[ \t]*$")
_MARKDOWN_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}(?!#)(?P<space>[ \t]+)?(?P<body>.*)$")
_MAX_LINK_DESTINATION_PAREN_DEPTH = 32


@dataclass(frozen=True, slots=True)
class _LexicalRanges:
    fences: tuple[OffsetRange, ...]
    html: tuple[OffsetRange, ...]
    roles: tuple[OffsetRange, ...]
    code: tuple[OffsetRange, ...]
    indented_code: tuple[OffsetRange, ...]
    display: tuple[DollarRange, ...]
    inline: tuple[DollarRange, ...]
    display_openers: tuple[int, ...]


class _RangeCursor:
    """Monotonic membership cursor for one ordered range sweep."""

    def __init__(self, ranges: Sequence[OffsetRange]) -> None:
        self._ranges = _merge_ranges(ranges)
        self._index = 0

    def end_at(self, position: int) -> int | None:
        while self._index < len(self._ranges) and self._ranges[self._index][1] <= position:
            self._index += 1
        if self._index >= len(self._ranges):
            return None
        start, end = self._ranges[self._index]
        return end if start <= position else None


@dataclass(frozen=True, slots=True)
class MarkdownLinkToken:
    start: int
    end: int
    is_image: bool
    fragment_target: str | None = None
    fragment_target_start: int | None = None
    fragment_target_end: int | None = None
    metadata_ranges: tuple[OffsetRange, ...] = ()


@dataclass(slots=True)
class _LinkFrame:
    token_start: int
    is_image: bool
    child_start: int


@dataclass(slots=True)
class _BlockContext:
    paragraph_active: bool = False
    list_content_columns: list[int] = field(default_factory=lambda: list[int]())
    list_container_ids: list[int] = field(default_factory=lambda: list[int]())


@dataclass(frozen=True, slots=True)
class _ListMarker:
    content_column: int
    content_index: int
    ordered_start: int | None
    has_content: bool

    def interrupts_paragraph(self) -> bool:
        return self.has_content and (self.ordered_start is None or self.ordered_start == 1)


@dataclass(frozen=True, slots=True)
class _ColumnContent:
    source_index: int
    text: str


@dataclass(frozen=True, slots=True)
class _ContainerLine:
    start: int
    end: int
    content_start: int
    content: str
    container_key: tuple[int, ...]
    block_start: bool


@dataclass(frozen=True, slots=True)
class _LineOwnership:
    indented_code: tuple[OffsetRange, ...]
    link_boundaries: tuple[int, ...]
    container_lines: tuple[_ContainerLine, ...]


@dataclass(frozen=True, slots=True)
class MarkdownReferenceSnapshot:
    """Immutable Markdown ownership decisions shared by reference consumers."""

    opaque_ranges: tuple[OffsetRange, ...]
    links: tuple[MarkdownLinkToken, ...]
    link_metadata_ranges: tuple[OffsetRange, ...]
    attached_target_labels: frozenset[str]


_FENCE_OPENER_RE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")


def parse_fence_opener(line: str) -> tuple[str, str] | None:
    """Return a valid fenced-code marker and info string for one source line."""

    match = _FENCE_OPENER_RE.fullmatch(line.rstrip("\r\n"))
    if match is None:
        return None
    marker = match.group("marker")
    info = match.group("info")
    if marker[0] == "`" and "`" in info:
        return None
    return marker, info


def is_fence_closer(line: str, marker: str) -> bool:
    """Return whether ``line`` is a CommonMark-style closer for ``marker``."""

    candidate = line.rstrip("\r\n")
    leading_spaces = len(candidate) - len(candidate.lstrip(" "))
    if leading_spaces > 3:
        return False
    candidate = candidate[leading_spaces:]
    marker_char = marker[0]
    run_length = 0
    while run_length < len(candidate) and candidate[run_length] == marker_char:
        run_length += 1
    return run_length >= len(marker) and not candidate[run_length:].strip(" \t")


def inline_code_ranges(
    text: str,
) -> tuple[OffsetRange, ...]:
    return _ordered_lexical_ranges(text, ()).code


def code_fence_ranges(
    text: str,
    occupied: Sequence[OffsetRange] = (),
) -> tuple[OffsetRange, ...]:
    return _ordered_lexical_ranges(text, occupied).fences


def _attached_markdown_target_labels_from_opaque(
    text: str,
    opaque: Sequence[OffsetRange],
    eligible_fence_starts: frozenset[int],
) -> frozenset[str]:
    lines = _source_lines(text)
    occupied_cursor = _RangeCursor(opaque)
    labels: set[str] = set()
    pending_label: str | None = None
    for start, _end, line in lines:
        occupied_end = occupied_cursor.end_at(start)
        if occupied_end is not None and start not in eligible_fence_starts:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--"):
            continue

        if pending_label is not None:
            if parse_fence_opener(line) is not None or _is_heading_line(line):
                labels.add(pending_label)
            pending_label = None

        anchor = _MARKDOWN_ANCHOR_RE.fullmatch(line)
        if anchor is not None:
            label = anchor.group("label").strip()
            pending_label = label[1:] if label.startswith("#") else label
    return frozenset(labels)


def dollar_display_ranges(
    text: str,
    occupied: Sequence[OffsetRange],
) -> tuple[DollarRange, ...]:
    return _ordered_lexical_ranges(text, occupied).display


def dollar_display_opener_positions(
    text: str,
    occupied: Sequence[OffsetRange],
) -> tuple[int, ...]:
    return _ordered_lexical_ranges(text, occupied).display_openers


def dollar_inline_ranges(
    text: str,
    occupied: Sequence[OffsetRange],
) -> tuple[DollarRange, ...]:
    return _ordered_lexical_ranges(text, occupied).inline


def is_escaped(text: str, index: int) -> bool:
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return slash_count % 2 == 1


def range_contains(position: int, ranges: Sequence[OffsetRange]) -> bool:
    """Return membership in source-ordered, non-overlapping ranges."""

    low = 0
    high = len(ranges)
    while low < high:
        middle = (low + high) // 2
        if ranges[middle][0] <= position:
            low = middle + 1
        else:
            high = middle
    if low == 0:
        return False
    start, end = ranges[low - 1]
    return start <= position < end


def _merge_ranges(ranges: Iterable[OffsetRange]) -> tuple[OffsetRange, ...]:
    merged: list[OffsetRange] = []
    for start, end in sorted((start, end) for start, end in ranges if start < end):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _ordered_lexical_ranges(
    text: str,
    occupied: Sequence[OffsetRange],
) -> _LexicalRanges:
    """Scan Markdown regions in source order so the first opener owns the text."""

    lines = _source_lines(text)
    if not lines:
        return _LexicalRanges((), (), (), (), (), (), (), ())

    ownership = _markdown_line_ownership(lines)
    container_lines = ownership.container_lines
    fences: list[OffsetRange] = []
    html: list[OffsetRange] = []
    roles: list[OffsetRange] = []
    code: list[OffsetRange] = []
    indented_code = ownership.indented_code
    display: list[DollarRange] = []
    inline: list[DollarRange] = []
    display_openers: list[int] = []
    occupied_cursor = _RangeCursor((*occupied, *indented_code))
    backtick_runs = _backtick_runs(text)
    next_same_backtick = _next_same_backtick_runs(backtick_runs)
    html_block_closes = _html_block_close_positions(text, container_lines)
    html_blank_ends = _container_html_blank_ends(container_lines)
    backtick_index = 0
    line_index = 0
    index = 0

    while index < len(text):
        while backtick_index < len(backtick_runs) and backtick_runs[backtick_index][0] < index:
            backtick_index += 1
        while line_index + 1 < len(lines) and index >= lines[line_index][1]:
            line_index += 1
        line_start, _line_end, line = lines[line_index]
        container_line = container_lines[line_index]
        line_content_end = line_start + len(line.rstrip("\r\n"))

        occupied_end = occupied_cursor.end_at(index)
        if occupied_end is not None:
            index = occupied_end
            continue

        if index == container_line.content_start and container_line.block_start:
            opener = parse_fence_opener(container_line.content)
            if opener is not None:
                marker, _info = opener
                close_index, boundary_index = _fence_close_index(
                    container_lines,
                    line_index,
                    marker,
                )
                if close_index is not None:
                    range_end = lines[close_index][1]
                elif boundary_index < len(lines):
                    range_end = lines[boundary_index][0]
                else:
                    range_end = len(text)
                fences.append((line_start, range_end))
                index = range_end
                continue

            if _starts_html_block(container_line.content):
                tag_start = text.find("<", container_line.content_start, container_line.end)
                if tag_start != -1 and not is_escaped(text, tag_start):
                    block = HTML_BLOCK_OPEN_RE.match(container_line.content)
                    html_end = _html_range_at(
                        text,
                        tag_start,
                        html_block_closes,
                        block_tag=block.group("tag").lower() if block is not None else None,
                        blank_line_end=html_blank_ends[line_index],
                    )
                    if html_end is not None:
                        html.append((line_start, html_end))
                        index = html_end
                        continue

        if text[index] == "{":
            role_end = _myst_role_end_at(text, index)
            if role_end is not None:
                roles.append((index, role_end))
                index = role_end
                continue

        if (index == line_start or text[index] == "<") and not is_escaped(text, index):
            html_end = _html_range_at(text, index, html_block_closes)
            if html_end is not None:
                html.append((index, html_end))
                index = html_end
                continue

        if text.startswith("$$", index) and _is_display_opener(text, index, line_start):
            display_openers.append(index)
            close = _find_ordered_display_close(text, index + 2)
            if close == -1:
                index = len(text)
                continue
            display.append((index, index + 2, close, close + 2))
            index = close + 2
            continue

        if text[index] == "$" and _is_inline_opening(text, index):
            close = _find_ordered_inline_close(text, index + 1, line_content_end)
            if close == -1:
                index = line_content_end
                continue
            inline.append((index, index + 1, close, close + 1))
            index = close + 1
            continue

        if text[index] != "`":
            index += 1
            continue

        if backtick_index >= len(backtick_runs):
            index += 1
            continue
        _run_start, run_end, _delimiter_length = backtick_runs[backtick_index]
        if is_escaped(text, index):
            index = run_end
            backtick_index += 1
            continue
        close_index = next_same_backtick[backtick_index]
        if close_index is None:
            index = run_end
            backtick_index += 1
            continue
        _, close_end, _ = backtick_runs[close_index]
        code.append((index, close_end))
        index = close_end
        backtick_index = close_index + 1

    return _LexicalRanges(
        # Starts are semantic: adjacent fences must remain distinct for lowering.
        fences=tuple(fences),
        html=_merge_ranges(html),
        roles=_merge_ranges(roles),
        code=_merge_ranges(code),
        indented_code=indented_code,
        display=tuple(display),
        inline=tuple(inline),
        display_openers=tuple(display_openers),
    )


def _source_lines(text: str) -> list[tuple[int, int, str]]:
    lines: list[tuple[int, int, str]] = []
    start = 0
    for raw_line in text.splitlines(keepends=True):
        end = start + len(raw_line)
        line = raw_line[:-1] if raw_line.endswith("\n") else raw_line
        lines.append((start, end, line))
        start = end
    return lines


def _markdown_line_ownership(
    lines: Sequence[tuple[int, int, str]],
) -> _LineOwnership:
    """Classify container-relative block ownership in one source-ordered pass."""

    ranges: list[OffsetRange] = []
    boundaries: list[int] = []
    container_lines: list[_ContainerLine] = []
    contexts: dict[int, _BlockContext] = {0: _BlockContext()}
    quote_paths: dict[int, tuple[int, ...]] = {0: ()}
    next_container_id = 0
    previous_depth = 0
    for start, end, raw_line in lines:
        line = raw_line.rstrip("\r")
        explicit_depth, quote_content_index = _block_quote_content(line)
        block_content = line[quote_content_index:]
        previous_context = contexts[previous_depth]
        previous_list_base = (
            previous_context.list_content_columns[-1]
            if previous_context.list_content_columns
            else 0
        )
        previous_relative = _content_after_columns(block_content, previous_list_base)
        depth = explicit_depth
        if (
            explicit_depth < previous_depth
            and block_content.strip(" \t")
            and previous_context.paragraph_active
            and not _starts_markdown_block(previous_relative.text, paragraph_active=True)
        ):
            # A nested quote paragraph may lazily continue with any suffix of its
            # explicit markers omitted; the source still belongs to the old path.
            depth = previous_depth
        else:
            if explicit_depth < previous_depth:
                for stale_depth in tuple(contexts):
                    if stale_depth > explicit_depth:
                        del contexts[stale_depth]
                for stale_depth in tuple(quote_paths):
                    if stale_depth > explicit_depth:
                        del quote_paths[stale_depth]
            if explicit_depth > previous_depth:
                # An explicit child quote is a block interruption; the parent
                # paragraph cannot resume after that child container closes.
                contexts[previous_depth].paragraph_active = False
                parent_path = (
                    *quote_paths[previous_depth],
                    *contexts[previous_depth].list_container_ids,
                )
                for quote_depth in range(previous_depth + 1, explicit_depth + 1):
                    next_container_id += 1
                    parent_path = (*parent_path, next_container_id)
                    quote_paths[quote_depth] = parent_path
                    contexts[quote_depth] = _BlockContext()

        if depth != previous_depth:
            boundaries.append(start)
        context = contexts.setdefault(depth, _BlockContext())
        if not block_content.strip(" \t"):
            boundaries.append(start)
            context.paragraph_active = False
            container_lines.append(
                _make_container_line(
                    start,
                    end,
                    quote_content_index,
                    _ColumnContent(0, block_content),
                    quote_paths[depth],
                    context,
                    block_start=False,
                )
            )
            previous_depth = depth
            continue

        indentation = _indent_columns(block_content)
        list_base = context.list_content_columns[-1] if context.list_content_columns else 0
        relative = (
            _content_after_columns(block_content, list_base)
            if indentation >= list_base
            else _ColumnContent(0, block_content)
        )

        paragraph_active = context.paragraph_active
        block_kind = _markdown_block_kind(relative.text, paragraph_active=paragraph_active)
        if paragraph_active and block_kind is None:
            container_lines.append(
                _make_container_line(
                    start,
                    end,
                    quote_content_index,
                    relative,
                    quote_paths[depth],
                    context,
                    block_start=False,
                )
            )
            previous_depth = depth
            continue
        context.paragraph_active = False

        original_list_depth = len(context.list_content_columns)
        while context.list_content_columns and indentation < context.list_content_columns[-1]:
            context.list_content_columns.pop()
            context.list_container_ids.pop()
        list_base = context.list_content_columns[-1] if context.list_content_columns else 0

        if context.list_content_columns and indentation >= list_base + 4:
            ranges.append((start, end))
            boundaries.append(start)
            container_lines.append(
                _make_container_line(
                    start,
                    end,
                    quote_content_index,
                    relative,
                    quote_paths[depth],
                    context,
                    block_start=False,
                )
            )
            previous_depth = depth
            continue

        relative = (
            _content_after_columns(block_content, list_base)
            if indentation >= list_base
            else _ColumnContent(0, block_content)
        )
        marker = _list_marker(relative.text)
        if marker is not None:
            content_column = list_base + marker.content_column
            context.list_content_columns.append(content_column)
            next_container_id += 1
            context.list_container_ids.append(next_container_id)
            item_content = _ColumnContent(
                relative.source_index + marker.content_index,
                relative.text[marker.content_index :],
            )
            item_is_code = marker.has_content and _indent_columns(item_content.text) >= 4
            context.paragraph_active = (
                marker.has_content
                and not item_is_code
                and _markdown_block_kind(item_content.text, paragraph_active=False) is None
            )
            boundaries.append(start)
            if item_is_code:
                ranges.append((start, end))
            container_lines.append(
                _make_container_line(
                    start,
                    end,
                    quote_content_index,
                    item_content,
                    quote_paths[depth],
                    context,
                    block_start=not item_is_code,
                )
            )
            previous_depth = depth
            continue

        if not context.list_content_columns and indentation >= 4:
            ranges.append((start, end))
            boundaries.append(start)
            container_lines.append(
                _make_container_line(
                    start,
                    end,
                    quote_content_index,
                    relative,
                    quote_paths[depth],
                    context,
                    block_start=False,
                )
            )
            previous_depth = depth
            continue

        block_kind = _markdown_block_kind(relative.text, paragraph_active=paragraph_active)
        if block_kind is not None:
            boundaries.append(start)
            if block_kind in {"heading", "setext", "thematic"}:
                boundaries.append(end)
        else:
            if len(context.list_content_columns) != original_list_depth:
                boundaries.append(start)
            context.paragraph_active = True
        container_lines.append(
            _make_container_line(
                start,
                end,
                quote_content_index,
                relative,
                quote_paths[depth],
                context,
                block_start=block_kind is not None,
            )
        )
        previous_depth = depth
    return _LineOwnership(
        indented_code=_merge_ranges(ranges),
        link_boundaries=tuple(sorted(set(boundaries))),
        container_lines=tuple(container_lines),
    )


def _make_container_line(
    start: int,
    end: int,
    quote_content_index: int,
    content: _ColumnContent,
    quote_path: tuple[int, ...],
    context: _BlockContext,
    *,
    block_start: bool,
) -> _ContainerLine:
    return _ContainerLine(
        start=start,
        end=end,
        content_start=start + quote_content_index + content.source_index,
        content=content.text,
        container_key=(*quote_path, *context.list_container_ids),
        block_start=block_start,
    )


def _indent_columns(line: str) -> int:
    columns = 0
    for char in line:
        if char == " ":
            columns += 1
        elif char == "\t":
            columns += 4 - columns % 4
        else:
            break
    return columns


def _content_after_columns(line: str, columns: int) -> _ColumnContent:
    index = 0
    current = 0
    while index < len(line) and current < columns and line[index] in " \t":
        if line[index] == " ":
            current += 1
        else:
            current += 4 - current % 4
        index += 1
    return _ColumnContent(index, " " * max(0, current - columns) + line[index:])


def _list_marker(line: str) -> _ListMarker | None:
    indentation = _indent_columns(line)
    if indentation > 3:
        return None
    index = len(line) - len(line.lstrip(" \t"))
    marker_start = index
    ordered_start: int | None = None
    if index < len(line) and line[index] in "*+-":
        index += 1
    else:
        digit_start = index
        while index < len(line) and index - digit_start < 9 and line[index] in "0123456789":
            index += 1
        if index == digit_start or index >= len(line) or line[index] not in ".)":
            return None
        ordered_start = int(line[digit_start:index])
        index += 1
    if index < len(line) and line[index] not in " \t":
        return None

    marker_width = index - marker_start
    marker_end_column = indentation + marker_width
    whitespace_start = index
    content_column = marker_end_column
    while index < len(line) and line[index] in " \t":
        if line[index] == " ":
            content_column += 1
        else:
            content_column += 4 - content_column % 4
        index += 1
    padding = content_column - marker_end_column
    if index == len(line) or padding == 0 or padding > 4:
        content_column = marker_end_column + 1
        content_index = min(len(line), whitespace_start + 1)
    else:
        assert index > whitespace_start
        content_index = index
    return _ListMarker(
        content_column=content_column,
        content_index=content_index,
        ordered_start=ordered_start,
        has_content=content_index < len(line),
    )


def _markdown_block_kind(line: str, *, paragraph_active: bool) -> str | None:
    if _is_heading_line(line):
        return "heading"
    if paragraph_active and _indent_columns(line) <= 3 and _is_setext_underline(line):
        return "setext"
    if _indent_columns(line) <= 3 and _is_thematic_break(line):
        return "thematic"
    marker = _list_marker(line)
    if marker is not None and (not paragraph_active or marker.interrupts_paragraph()):
        return "list"
    if parse_fence_opener(line) is not None:
        return "fence"
    if _starts_html_block(line):
        return "html"
    if _starts_display_block(line):
        return "display"
    return None


def _starts_markdown_block(line: str, *, paragraph_active: bool) -> bool:
    return _markdown_block_kind(line, paragraph_active=paragraph_active) is not None


def _is_heading_line(line: str) -> bool:
    if _indent_columns(line) > 3:
        return False
    match = _MARKDOWN_HEADING_RE.fullmatch(line)
    if match is None:
        return False
    return match.group("space") is not None or not match.group("body")


def _fence_close_index(
    lines: Sequence[_ContainerLine],
    opener_index: int,
    marker: str,
) -> tuple[int | None, int]:
    """Return ``(closer_index, boundary_index)`` for the opener's path."""

    opener_path = lines[opener_index].container_key
    for index in range(opener_index + 1, len(lines)):
        candidate_path = lines[index].container_key
        if candidate_path[: len(opener_path)] != opener_path:
            return None, index
        if candidate_path == opener_path and is_fence_closer(
            lines[index].content,
            marker,
        ):
            return index, index
    return None, len(lines)


def _backtick_run_end(text: str, start: int) -> int:
    end = start
    while end < len(text) and text[end] == "`":
        end += 1
    return end


def _backtick_runs(text: str) -> tuple[tuple[int, int, int], ...]:
    runs: list[tuple[int, int, int]] = []
    index = 0
    while index < len(text):
        if text[index] != "`":
            index += 1
            continue
        run_end = _backtick_run_end(text, index)
        runs.append((index, run_end, run_end - index))
        index = run_end
    return tuple(runs)


def _next_same_backtick_runs(
    runs: Sequence[tuple[int, int, int]],
) -> tuple[int | None, ...]:
    next_runs: list[int | None] = [None] * len(runs)
    last_by_length: dict[int, int] = {}
    for index in range(len(runs) - 1, -1, -1):
        length = runs[index][2]
        next_runs[index] = last_by_length.get(length)
        last_by_length[length] = index
    return tuple(next_runs)


def _is_display_opener(text: str, start: int, line_start: int) -> bool:
    indentation = start - line_start
    return (
        indentation <= 3
        and all(text[index] == " " for index in range(line_start, start))
        and (start + 2 == len(text) or text[start + 2] != "$")
    )


def _find_ordered_display_close(text: str, start: int) -> int:
    line_start = start
    while line_start < len(text):
        line_end = text.find("\n", line_start)
        if line_end == -1:
            line_end = len(text)
        candidate = _display_close_on_line(text, line_start, line_end)
        if candidate != -1:
            return candidate
        if line_end == len(text):
            return -1
        line_start = line_end + 1
    return -1


def _display_close_on_line(text: str, start: int, end: int) -> int:
    content_end = end
    while content_end > start and text[content_end - 1] in "\r \t":
        content_end -= 1

    label_start = content_end
    if content_end > start and text[content_end - 1] == "}":
        label_start = text.rfind("{#", start, content_end)
        if (
            label_start == -1
            or label_start + 2 >= content_end - 1
            or any(
                char == "}" or char.isspace() for char in text[label_start + 2 : content_end - 1]
            )
        ):
            label_start = content_end
    elif content_end > start and text[content_end - 1] == ")":
        label_start = text.rfind("(", start, content_end)
        if (
            label_start == -1
            or label_start + 1 >= content_end - 1
            or any(
                char in "()" or char.isspace() for char in text[label_start + 1 : content_end - 1]
            )
        ):
            label_start = content_end

    candidate_end = label_start
    while candidate_end > start and text[candidate_end - 1] in "\r \t":
        candidate_end -= 1
    candidate = candidate_end - 2
    if candidate < start or not text.startswith("$$", candidate):
        return -1
    if is_escaped(text, candidate):
        return -1
    if candidate > 0 and text[candidate - 1] == "$":
        return -1
    return candidate


def _myst_role_end_at(text: str, start: int) -> int | None:
    if is_escaped(text, start):
        return None
    match = _MYST_ROLE_RE.match(text, start)
    return match.end() if match is not None else None


def _html_range_at(
    text: str,
    start: int,
    block_closes: dict[int, int],
    *,
    block_tag: str | None = None,
    blank_line_end: int | None = None,
) -> int | None:
    for pattern in (
        HTML_COMMENT_RE,
        HTML_DECLARATION_RE,
        HTML_PROCESSING_INSTRUCTION_RE,
        HTML_CDATA_RE,
    ):
        match = pattern.match(text, start)
        if match is not None:
            return match.end()

    if block_tag is not None:
        closing = block_closes.get(start)
        if closing is not None:
            return closing
        if block_tag in HTML_RAWTEXT_TAGS:
            return len(text)
        assert blank_line_end is not None
        return blank_line_end

    tag = HTML_TAG_RE.match(text, start)
    return tag.end() if tag is not None else None


def _container_html_blank_ends(lines: Sequence[_ContainerLine]) -> tuple[int, ...]:
    ends = [lines[-1].end] * len(lines)
    next_end = lines[-1].end
    for index in range(len(lines) - 2, -1, -1):
        next_line = lines[index + 1]
        if next_line.container_key != lines[index].container_key or not next_line.content.strip(
            " \t"
        ):
            next_end = next_line.start
        ends[index] = next_end
    return tuple(ends)


def _html_block_close_positions(
    text: str,
    lines: Sequence[_ContainerLine],
) -> dict[int, int]:
    candidates_by_tag: dict[str, list[int]] = {}
    for line in lines:
        if not line.block_start:
            continue
        match = HTML_BLOCK_OPEN_RE.match(line.content)
        if match is None:
            continue
        tag_start = text.find("<", line.content_start, line.end)
        assert tag_start != -1
        candidates_by_tag.setdefault(match.group("tag").lower(), []).append(tag_start)
    if not candidates_by_tag:
        return {}

    events_by_tag: dict[str, list[tuple[int, int, bool, bool, bool]]] = {
        tag: [] for tag in candidates_by_tag
    }
    for match in HTML_TAG_EVENT_RE.finditer(text):
        tag = match.group("tag").lower()
        if tag not in events_by_tag:
            continue
        closing = match.group("closing") is not None
        tail = match.group("tail")
        events_by_tag[tag].append(
            (
                match.start(),
                match.end(),
                closing,
                not closing and tail.rstrip().endswith("/"),
                closing and not tail.strip(),
            )
        )

    closes: dict[int, int] = {}
    for tag, candidates in candidates_by_tag.items():
        events = events_by_tag[tag]
        if tag in HTML_RAWTEXT_TAGS:
            close_index = 0
            raw_closes = [event for event in events if event[4]]
            for candidate in candidates:
                while close_index < len(raw_closes) and raw_closes[close_index][0] <= candidate:
                    close_index += 1
                if close_index < len(raw_closes):
                    closes[candidate] = raw_closes[close_index][1]
            continue

        stack: list[int] = []
        pending: dict[int, list[int]] = {}
        candidate_index = 0
        event_index = 0
        while candidate_index < len(candidates) or event_index < len(events):
            candidate = (
                candidates[candidate_index] if candidate_index < len(candidates) else len(text)
            )
            event = events[event_index] if event_index < len(events) else None
            event_start = event[0] if event is not None else len(text)
            position = min(candidate, event_start)
            is_candidate = candidate == position
            is_event = event_start == position

            # Incomplete and self-closing block openers historically use the next
            # same-tag close at their current nesting depth, without becoming nested.
            if is_candidate and (not is_event or event is None or event[2] or event[3]):
                pending.setdefault(len(stack), []).append(candidate)
            if is_event and event is not None:
                _start, end, closing, self_closing, _raw_closing = event
                if closing:
                    depth = len(stack)
                    if stack:
                        closes[stack.pop()] = end
                    for pending_start in pending.pop(depth, []):
                        closes[pending_start] = end
                elif not self_closing:
                    stack.append(event_start)

            if is_candidate:
                candidate_index += 1
            if is_event:
                event_index += 1
    return closes


def _is_adjacent_to_dollar(text: str, index: int) -> bool:
    return (index > 0 and text[index - 1] == "$") or (
        index + 1 < len(text) and text[index + 1] == "$"
    )


def _is_inline_opening(text: str, index: int) -> bool:
    return not is_escaped(text, index) and not _is_adjacent_to_dollar(text, index)


def _is_inline_closing(text: str, index: int) -> bool:
    return not is_escaped(text, index) and not _is_adjacent_to_dollar(text, index)


def _find_ordered_inline_close(text: str, start: int, line_end: int) -> int:
    index = start
    while index < line_end:
        if text[index] == "$" and _is_inline_closing(text, index):
            return index
        index += 1
    return -1


def markdown_reference_snapshot(text: str) -> MarkdownReferenceSnapshot:
    """Return one immutable lexical/reference snapshot for ``text``."""

    baseline_lexical = _ordered_lexical_ranges(text, ())
    baseline_opaque = _opaque_ranges_from_lexical(baseline_lexical, len(text))
    baseline_cursor = _RangeCursor((*baseline_opaque, *baseline_lexical.roles))
    candidate_metadata_ranges: list[OffsetRange] = []
    for token in _markdown_link_tokens_from_lexical(text, ()):
        if baseline_cursor.end_at(token.start) is not None:
            continue
        for start, end in token.metadata_ranges:
            if baseline_cursor.end_at(start) is None:
                candidate_metadata_ranges.append((start, end))

    # Metadata that starts before a lexical opener owns that opener. Conversely,
    # a link-like candidate cannot escape an owner that started before the link
    # or its metadata.
    candidate_metadata = _merge_ranges(candidate_metadata_ranges)
    lexical = _ordered_lexical_ranges(text, candidate_metadata)
    lexical_opaque = _opaque_ranges_from_lexical(lexical, len(text))
    protected = (*lexical_opaque, *lexical.roles)
    links = _markdown_link_tokens_from_lexical(text, protected)
    link_metadata = _metadata_ranges_from_tokens(links)
    opaque = _merge_ranges((*lexical_opaque, *link_metadata))
    return MarkdownReferenceSnapshot(
        opaque_ranges=opaque,
        links=links,
        link_metadata_ranges=link_metadata,
        attached_target_labels=_attached_markdown_target_labels_from_opaque(
            text,
            opaque,
            frozenset(start for start, _end in lexical.fences),
        ),
    )


def _markdown_link_tokens_from_lexical(
    text: str,
    protected: Sequence[OffsetRange],
) -> tuple[MarkdownLinkToken, ...]:
    tokens: list[MarkdownLinkToken] = []
    non_image_prefix = [0]
    metadata_ranges: list[OffsetRange] = []
    metadata_prefix = [0]
    protected_cursor = _RangeCursor(protected)
    stack: list[_LinkFrame] = []
    boundaries = _link_label_boundaries(text)
    boundary_index = 0
    index = 0
    while index < len(text):
        while boundary_index < len(boundaries) and boundaries[boundary_index] <= index:
            stack.clear()
            boundary_index += 1

        protected_end = protected_cursor.end_at(index)
        if protected_end is not None:
            index = protected_end
            continue

        char = text[index]
        if char == "\\":
            index = _skip_backslash_escape(text, index)
            continue
        if char == "!" and index + 1 < len(text) and text[index + 1] == "[":
            stack.append(_LinkFrame(index, True, len(tokens)))
            index += 2
            continue
        if char == "[":
            stack.append(_LinkFrame(index, False, len(tokens)))
            index += 1
            continue
        if char != "]" or not stack:
            index += 1
            continue

        frame = stack.pop()
        next_index = index + 1
        if index + 1 < len(text) and text[index + 1] == "(":
            limit = boundaries[boundary_index] if boundary_index < len(boundaries) else len(text)
            body = _parse_link_body(text, index + 2, limit)
            if body is not None:
                destination_start, destination_end, end = body
                child_non_image_count = (
                    non_image_prefix[len(tokens)] - non_image_prefix[frame.child_start]
                )
                if frame.is_image or child_non_image_count == 0:
                    child_metadata_start = metadata_prefix[frame.child_start]
                    child_metadata_end = metadata_prefix[len(tokens)]
                    child_metadata_ranges = (
                        metadata_ranges[offset]
                        for offset in range(child_metadata_start, child_metadata_end)
                    )
                    token = _make_link_token(
                        text,
                        frame.token_start,
                        end,
                        destination_start,
                        destination_end,
                        frame.is_image,
                        child_metadata_ranges,
                    )
                    surviving_metadata_end = metadata_prefix[frame.child_start]
                    del tokens[frame.child_start :]
                    del non_image_prefix[frame.child_start + 1 :]
                    del metadata_prefix[frame.child_start + 1 :]
                    del metadata_ranges[surviving_metadata_end:]
                    tokens.append(token)
                    non_image_prefix.append(non_image_prefix[-1] + int(not token.is_image))
                    metadata_ranges.extend(token.metadata_ranges)
                    metadata_prefix.append(len(metadata_ranges))
                next_index = end
        index = next_index

    return tuple(sorted(tokens, key=lambda token: token.start))


def _link_label_boundaries(text: str) -> tuple[int, ...]:
    return _markdown_line_ownership(_source_lines(text)).link_boundaries


def _block_quote_content(line: str) -> tuple[int, int]:
    depth = 0
    index = 0
    while True:
        marker = index
        while marker < len(line) and marker - index < 3 and line[marker] == " ":
            marker += 1
        if marker >= len(line) or line[marker] != ">":
            return depth, index
        depth += 1
        index = marker + 1
        if index < len(line) and line[index] in " \t":
            index += 1


def _is_setext_underline(line: str) -> bool:
    candidate = line.strip(" \t")
    return (
        bool(candidate) and candidate[0] in "=-" and all(char == candidate[0] for char in candidate)
    )


def _is_thematic_break(line: str) -> bool:
    candidate = line.strip(" \t")
    if (
        not candidate
        or candidate[0] not in "*_-"
        or any(char not in {candidate[0], " ", "\t"} for char in candidate)
    ):
        return False
    marker_count = sum(char == candidate[0] for char in candidate)
    return marker_count >= 3


def _starts_html_block(line: str) -> bool:
    candidate = line.lstrip(" \t")
    if len(line) - len(candidate) > 3:
        return False
    return (
        HTML_BLOCK_OPEN_RE.match(line) is not None
        or candidate.startswith(("<!--", "<?", "<![CDATA["))
        or re.match(r"<![A-Z]", candidate, re.IGNORECASE) is not None
    )


def _starts_display_block(line: str) -> bool:
    candidate = line.lstrip(" ")
    return (
        len(line) - len(candidate) <= 3
        and candidate.startswith("$$")
        and not candidate.startswith("$$$")
    )


def _make_link_token(
    text: str,
    token_start: int,
    end: int,
    destination_start: int,
    destination_end: int,
    is_image: bool,
    child_metadata_ranges: Iterable[OffsetRange],
) -> MarkdownLinkToken:
    destination, decoded_spans = _decode_destination_span(text, destination_start, destination_end)
    fragment_target: str | None = None
    fragment_target_start: int | None = None
    fragment_target_end: int | None = None
    if destination.startswith("#") and len(destination) > 1:
        fragment_target = destination[1:]
        fragment_target_start = decoded_spans[1][0]
        fragment_target_end = decoded_spans[-1][1]
    if is_image:
        metadata_ranges = ((token_start, end),)
    else:
        metadata_ranges = _merge_ranges(chain(((destination_start, end),), child_metadata_ranges))
    return MarkdownLinkToken(
        start=token_start,
        end=end,
        is_image=is_image,
        fragment_target=fragment_target,
        fragment_target_start=fragment_target_start,
        fragment_target_end=fragment_target_end,
        metadata_ranges=metadata_ranges,
    )


def _decode_destination_span(
    text: str,
    start: int,
    end: int,
) -> tuple[str, tuple[tuple[int, int], ...]]:
    decoded: list[str] = []
    spans: list[tuple[int, int]] = []
    index = start
    while index < end:
        if text[index] == "\\" and index + 1 < end and _is_ascii_punctuation(text[index + 1]):
            decoded.append(text[index + 1])
            spans.append((index, index + 2))
            index += 2
            continue
        entity_end = _entity_end_at(text, index, end) if text[index] == "&" else None
        if entity_end is not None:
            entity = text[index : entity_end + 1]
            decoded_entity = _decode_entity(entity)
            if decoded_entity is not None:
                decoded.extend(decoded_entity)
                spans.extend((index, entity_end + 1) for _ in decoded_entity)
                index = entity_end + 1
                continue
        decoded.append(text[index])
        spans.append((index, index + 1))
        index += 1
    return "".join(decoded), tuple(spans)


def _entity_end_at(text: str, start: int, end: int) -> int | None:
    cursor = start + 1
    if cursor >= end:
        return None
    if text[cursor] == "#":
        cursor += 1
        is_hex = cursor < end and text[cursor] in "xX"
        if is_hex:
            cursor += 1
        digits_start = cursor
        valid_digits = "0123456789abcdefABCDEF" if is_hex else "0123456789"
        max_digits = 6 if is_hex else 7
        while cursor < end and cursor - digits_start < max_digits and text[cursor] in valid_digits:
            cursor += 1
        if cursor == digits_start:
            return None
    else:
        name_start = cursor
        while cursor < end and text[cursor].isascii() and text[cursor].isalnum():
            cursor += 1
        if cursor == name_start:
            return None
    return cursor if cursor < end and text[cursor] == ";" else None


def _metadata_ranges_from_tokens(
    tokens: Sequence[MarkdownLinkToken],
) -> tuple[OffsetRange, ...]:
    ranges: list[OffsetRange] = []
    for token in tokens:
        ranges.extend(token.metadata_ranges)
    return _merge_ranges(ranges)


def _opaque_ranges_from_lexical(
    lexical: _LexicalRanges,
    text_length: int,
) -> tuple[OffsetRange, ...]:
    ranges = [*lexical.fences, *lexical.html, *lexical.code, *lexical.indented_code]
    ranges.extend(
        (start, close_end) for start, _body_start, _body_end, close_end in lexical.display
    )
    ranges.extend((start, close_end) for start, _body_start, _body_end, close_end in lexical.inline)
    closed_display_starts = {start for start, _body_start, _body_end, _end in lexical.display}
    ranges.extend(
        (start, text_length)
        for start in lexical.display_openers
        if start not in closed_display_starts
    )
    return _merge_ranges(ranges)


def _parse_link_body(text: str, start: int, limit: int) -> tuple[int, int, int] | None:
    index, _ = _skip_link_whitespace(text, start, limit)
    if index is None:
        return None
    if index < limit and text[index] == "<":
        destination_start = index + 1
        index += 1
        while index < limit:
            if text[index] == "\\":
                index = _skip_backslash_escape(text, index)
                continue
            if text[index] == "<":
                return None
            if text[index] == ">":
                destination_end = index
                index += 1
                break
            if text[index] in " \t\n\r" or _is_ascii_control(text[index]):
                return None
            index += 1
        else:
            return None
    else:
        destination_start = index
        depth = 0
        while index < limit:
            char = text[index]
            if char == "\\":
                index = _skip_backslash_escape(text, index)
                continue
            if char in " \t\n\r":
                if depth:
                    return None
                break
            if _is_ascii_control(char):
                return None
            if char == "(":
                depth += 1
                if depth > _MAX_LINK_DESTINATION_PAREN_DEPTH:
                    return None
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            index += 1
        if depth != 0:
            return None
        destination_end = index

    index, has_separator = _skip_link_whitespace(text, index, limit)
    if index is None or index >= limit:
        return None
    if text[index] != ")":
        if not has_separator:
            return None
        index = _parse_link_title(text, index, limit)
        if index is None:
            return None
        index, _ = _skip_link_whitespace(text, index, limit)
        if index is None or index >= limit or text[index] != ")":
            return None
    return destination_start, destination_end, index + 1


def _parse_link_title(text: str, start: int, limit: int) -> int | None:
    opener = text[start]
    if opener in {'"', "'"}:
        index = start + 1
        while index < limit:
            if text[index] == "\\":
                index = _skip_backslash_escape(text, index)
                continue
            if text[index] == opener:
                return index + 1
            if text[index] in "\n\r":
                index = _advance_line_ending(text, index)
                if _starts_blank_line(text, index, limit):
                    return None
                continue
            index += 1
        return None
    if opener != "(":
        return None
    index = start + 1
    while index < limit:
        if text[index] == "\\":
            index = _skip_backslash_escape(text, index)
            continue
        if text[index] in "\n\r":
            index = _advance_line_ending(text, index)
            if _starts_blank_line(text, index, limit):
                return None
            continue
        if text[index] == "(":
            return None
        if text[index] == ")":
            return index + 1
        index += 1
    return None


def _skip_link_whitespace(text: str, start: int, limit: int) -> tuple[int | None, bool]:
    index = start
    while index < limit and text[index] in " \t":
        index += 1
    if index >= limit or text[index] not in "\n\r":
        return index, index != start
    index = _advance_line_ending(text, index)
    while index < limit and text[index] in " \t":
        index += 1
    return (None, True) if index < limit and text[index] in "\n\r" else (index, True)


def _advance_line_ending(text: str, index: int) -> int:
    if text.startswith("\r\n", index):
        return index + 2
    assert index < len(text)
    assert text[index] in "\n\r"
    return index + 1


def _starts_blank_line(text: str, index: int, limit: int) -> bool:
    while index < limit and text[index] in " \t":
        index += 1
    return index < limit and text[index] in "\n\r"


def _is_ascii_control(char: str) -> bool:
    return ord(char) < 0x20 or ord(char) == 0x7F


def _skip_backslash_escape(text: str, index: int) -> int:
    if index + 1 < len(text) and _is_ascii_punctuation(text[index + 1]):
        return index + 2
    return index + 1


def _is_ascii_punctuation(char: str) -> bool:
    return "!" <= char <= "/" or ":" <= char <= "@" or "[" <= char <= "`" or "{" <= char <= "~"


def _decode_entity(value: str) -> str | None:
    if value.startswith("&") and value[1:-1].startswith("#"):
        decoded = unescape(value)
    elif (decoded_entity := html5.get(value[1:])) is not None:
        decoded = decoded_entity
    else:
        return None
    return decoded if decoded != value else None
