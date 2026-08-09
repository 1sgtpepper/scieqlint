"""Shared ordered lexical semantics for Markdown opaque regions and math."""

from __future__ import annotations

import re
from collections.abc import Sequence

OffsetRange = tuple[int, int]
DollarRange = tuple[int, int, int, int]

_FENCE_OPENER_RE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
HTML_COMMENT_RE = re.compile(r"<!--.*?(?:-->|$)", re.DOTALL)
HTML_DECLARATION_RE = re.compile(r"<![A-Z][^>]*?(?:>|$)", re.IGNORECASE | re.DOTALL)
HTML_PROCESSING_INSTRUCTION_RE = re.compile(r"<\?.*?(?:\?>|$)", re.DOTALL)
HTML_CDATA_RE = re.compile(r"<!\[CDATA\[.*?(?:\]\]>|$)", re.DOTALL)
HTML_ELEMENT_RE = re.compile(
    r"<(?P<tag>[A-Za-z][A-Za-z0-9:-]*)\b[^>]*>.*?</(?P=tag)[ \t]*>",
    re.IGNORECASE | re.DOTALL,
)
HTML_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9:-]*(?:\s+[^<>]*?)?/?>", re.IGNORECASE)
HTML_BLOCK_OPEN_RE = re.compile(
    r"^[ \t]{0,3}<(?P<tag>address|article|aside|base|basefont|blockquote|body|caption|"
    r"center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|"
    r"footer|form|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|"
    r"nav|ol|p|pre|script|section|summary|table|tbody|td|tfoot|th|thead|title|tr|"
    r"track|ul)(?:[ \t/>]|$)",
    re.IGNORECASE | re.MULTILINE,
)
HTML_RAWTEXT_TAGS = frozenset({"script", "style", "textarea", "title"})


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
    occupied: Sequence[OffsetRange] = (),
) -> tuple[OffsetRange, ...]:
    blocked = _merge_ranges((*occupied, *code_fence_ranges(text)))
    return _scan_inline_code_ranges(text, blocked)


def _scan_inline_code_ranges(
    text: str,
    blocked: Sequence[OffsetRange],
) -> tuple[OffsetRange, ...]:
    ranges: list[OffsetRange] = []
    index = 0
    while index < len(text):
        blocked_end = _range_end_at(index, blocked)
        if blocked_end is not None:
            index = blocked_end
            continue
        if text[index] != "`":
            index += 1
            continue
        opener_end = _backtick_run_end(text, index)
        delimiter_length = opener_end - index
        close_start = _matching_backtick_run(text, opener_end, delimiter_length, blocked)
        if close_start is None:
            index = opener_end
            continue
        close_end = close_start + delimiter_length
        ranges.append((index, close_end))
        index = close_end
    return tuple(ranges)


def code_fence_ranges(text: str) -> tuple[OffsetRange, ...]:
    lines: list[tuple[int, int, str]] = []
    start = 0
    for line in text.splitlines(keepends=True):
        end = start + len(line)
        lines.append((start, end, line[:-1] if line.endswith("\n") else line))
        start = end

    ranges: list[OffsetRange] = []
    index = 0
    while index < len(lines):
        opener_start, _opener_end, opener_line = lines[index]
        opener = parse_fence_opener(opener_line)
        if opener is None:
            index += 1
            continue
        marker, _info = opener
        close_index = _fence_close_index(lines, index, marker)
        range_end = lines[close_index][1] if close_index is not None else len(text)
        ranges.append((opener_start, range_end))
        index = close_index + 1 if close_index is not None else len(lines)
    return tuple(ranges)


def markdown_protected_ranges(
    text: str,
    occupied: Sequence[OffsetRange] = (),
) -> tuple[OffsetRange, ...]:
    """Return ordered non-math Markdown regions that delimit live scanning."""

    fences = code_fence_ranges(text)
    blocked = _merge_ranges((*occupied, *fences))
    inline_and_html = _inline_and_html_ranges(text, blocked)
    return _merge_ranges((*occupied, *fences, *inline_and_html))


def _inline_and_html_ranges(
    text: str,
    blocked: Sequence[OffsetRange],
) -> tuple[OffsetRange, ...]:
    ranges: list[OffsetRange] = []
    index = 0
    while index < len(text):
        blocked_end = _range_end_at(index, blocked)
        if blocked_end is not None:
            index = blocked_end
            continue
        html_end = _html_range_at(text, index)
        if html_end is not None:
            ranges.append((index, html_end))
            index = html_end
            continue
        if text[index] != "`":
            index += 1
            continue
        opener_end = _backtick_run_end(text, index)
        delimiter_length = opener_end - index
        close_start = _matching_backtick_run(text, opener_end, delimiter_length, blocked)
        if close_start is None:
            index = opener_end
            continue
        close_end = close_start + delimiter_length
        ranges.append((index, close_end))
        index = close_end
    return tuple(ranges)


def dollar_display_ranges(
    text: str,
    occupied: Sequence[OffsetRange],
) -> tuple[DollarRange, ...]:
    ranges: list[DollarRange] = []
    cursor = 0
    while True:
        start = text.find("$$", cursor)
        if start == -1:
            break
        if (
            _in_ranges(start, occupied)
            or is_escaped(text, start)
            or not _is_display_opener(text, start)
        ):
            cursor = start + 2
            continue
        close = _find_dollar_close(text, start + 2, occupied)
        if close == -1:
            cursor = start + 2
            continue
        ranges.append((start, start + 2, close, close + 2))
        cursor = close + 2
    return tuple(ranges)


def dollar_display_opener_positions(
    text: str,
    occupied: Sequence[OffsetRange],
) -> tuple[int, ...]:
    positions: list[int] = []
    cursor = 0
    while True:
        start = text.find("$$", cursor)
        if start == -1:
            break
        if (
            not _in_ranges(start, occupied)
            and not is_escaped(text, start)
            and _is_display_opener(text, start)
        ):
            positions.append(start)
        cursor = start + 2
    return tuple(positions)


def dollar_inline_ranges(
    text: str,
    occupied: Sequence[OffsetRange],
) -> tuple[DollarRange, ...]:
    ranges: list[DollarRange] = []
    line_start = 0
    while line_start < len(text):
        line_end = text.find("\n", line_start)
        if line_end == -1:
            line_end = len(text)
        opening: int | None = None
        index = line_start
        while index < line_end:
            occupied_end = _range_end_at(index, occupied)
            if occupied_end is not None:
                opening = None
                index = min(occupied_end, line_end)
                continue
            if text[index] != "$":
                index += 1
                continue
            if opening is None:
                if _is_inline_opening(text, index):
                    opening = index
                index += 1
                continue
            if _is_inline_closing(text, index):
                if index > opening + 1:
                    ranges.append((opening, opening + 1, index, index + 1))
                opening = None
            index += 1
        line_start = line_end + 1
    return tuple(ranges)


def is_escaped(text: str, index: int) -> bool:
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return slash_count % 2 == 1


def _in_ranges(position: int, ranges: Sequence[OffsetRange]) -> bool:
    return any(start <= position < end for start, end in ranges)


def _range_end_at(position: int, ranges: Sequence[OffsetRange]) -> int | None:
    for start, end in ranges:
        if start <= position < end:
            return end
        if start > position:
            break
    return None


def _merge_ranges(ranges: Sequence[OffsetRange]) -> tuple[OffsetRange, ...]:
    merged: list[OffsetRange] = []
    for start, end in sorted((start, end) for start, end in ranges if start < end):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _fence_close_index(
    lines: Sequence[tuple[int, int, str]],
    opener_index: int,
    marker: str,
) -> int | None:
    for index in range(opener_index + 1, len(lines)):
        if is_fence_closer(lines[index][2], marker):
            return index
    return None


def _backtick_run_end(text: str, start: int) -> int:
    end = start
    while end < len(text) and text[end] == "`":
        end += 1
    return end


def _matching_backtick_run(
    text: str,
    start: int,
    length: int,
    blocked: Sequence[OffsetRange],
) -> int | None:
    index = start
    while index < len(text):
        if _range_end_at(index, blocked) is not None:
            return None
        if text[index] != "`":
            index += 1
            continue
        run_end = _backtick_run_end(text, index)
        if run_end - index == length:
            return index
        index = run_end
    return None


def _is_display_opener(text: str, start: int) -> bool:
    line_start = text.rfind("\n", 0, start) + 1
    prefix = text[line_start:start]
    return (
        len(prefix) <= 3
        and not prefix.strip(" ")
        and (start + 2 == len(text) or text[start + 2] != "$")
    )


def _find_dollar_close(
    text: str,
    start: int,
    occupied: Sequence[OffsetRange],
) -> int:
    cursor = start
    while True:
        close = text.find("$$", cursor)
        if close == -1:
            return -1
        if any(
            range_start < close + 2 and range_end > cursor for range_start, range_end in occupied
        ):
            return -1
        if (
            not is_escaped(text, close)
            and (close == 0 or text[close - 1] != "$")
            and (close + 2 == len(text) or text[close + 2] != "$")
        ):
            return close
        cursor = close + 2


def _html_range_at(text: str, start: int) -> int | None:
    for pattern in (
        HTML_COMMENT_RE,
        HTML_DECLARATION_RE,
        HTML_PROCESSING_INSTRUCTION_RE,
        HTML_CDATA_RE,
        HTML_ELEMENT_RE,
    ):
        match = pattern.match(text, start)
        if match is not None:
            return match.end()

    block = HTML_BLOCK_OPEN_RE.match(text, start)
    if block is not None:
        tag = block.group("tag").lower()
        closing = re.search(
            rf"</[ \t]*{re.escape(tag)}[ \t]*>",
            text[block.end() :],
            re.IGNORECASE,
        )
        if closing is not None:
            return block.end() + closing.end()
        if tag in HTML_RAWTEXT_TAGS:
            return len(text)
        blank_line = re.search(r"\n[ \t]*\n", text[block.end() :])
        return len(text) if blank_line is None else block.end() + blank_line.start() + 1

    tag = HTML_TAG_RE.match(text, start)
    return tag.end() if tag is not None else None


def _is_adjacent_to_dollar(text: str, index: int) -> bool:
    return (index > 0 and text[index - 1] == "$") or (
        index + 1 < len(text) and text[index + 1] == "$"
    )


def _is_inline_opening(text: str, index: int) -> bool:
    if is_escaped(text, index) or _is_adjacent_to_dollar(text, index):
        return False
    return index == 0 or not (text[index - 1].isalnum() or text[index - 1] == "_")


def _is_inline_closing(text: str, index: int) -> bool:
    if is_escaped(text, index) or _is_adjacent_to_dollar(text, index):
        return False
    return index + 1 == len(text) or not (text[index + 1].isalnum() or text[index + 1] == "_")
