"""Shared dollar-delimiter and Markdown code-span lexical semantics."""

from __future__ import annotations

import re
from collections.abc import Sequence

OffsetRange = tuple[int, int]
DollarRange = tuple[int, int, int, int]

INLINE_CODE_RE = re.compile(r"(?P<ticks>`+)[^`\n]*(?P=ticks)")
CODE_FENCE_RE = re.compile(r"^[ \t]{0,3}(?P<marker>`{3,}|~{3,})[^\n]*$")


def inline_code_ranges(text: str) -> tuple[OffsetRange, ...]:
    return tuple((match.start(), match.end()) for match in INLINE_CODE_RE.finditer(text))


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
        match = CODE_FENCE_RE.match(opener_line)
        if match is None:
            index += 1
            continue
        marker = match.group("marker")
        close_index = _fence_close_index(lines, index, marker)
        range_end = lines[close_index][1] if close_index is not None else len(text)
        ranges.append((opener_start, range_end))
        index = close_index + 1 if close_index is not None else len(lines)
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
        for index in range(line_start, line_end):
            if text[index] != "$" or _in_ranges(index, occupied):
                continue
            if opening is None:
                if _is_inline_opening(text, index):
                    opening = index
                continue
            if _is_inline_closing(text, index):
                if index > opening + 1:
                    ranges.append((opening, opening + 1, index, index + 1))
                opening = None
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


def _fence_close_index(
    lines: Sequence[tuple[int, int, str]],
    opener_index: int,
    marker: str,
) -> int | None:
    fence_char = marker[0]
    fence_length = len(marker)
    for index in range(opener_index + 1, len(lines)):
        stripped = lines[index][2].strip()
        if stripped.startswith(fence_char * fence_length) and set(stripped) <= {fence_char}:
            return index
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
        if (
            not _in_ranges(close, occupied)
            and not is_escaped(text, close)
            and (close == 0 or text[close - 1] != "$")
            and (close + 2 == len(text) or text[close + 2] != "$")
        ):
            return close
        cursor = close + 2


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
