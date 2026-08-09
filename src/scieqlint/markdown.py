"""Shared dollar-delimiter and Markdown code-span lexical semantics."""

from __future__ import annotations

import re
from collections.abc import Sequence

OffsetRange = tuple[int, int]
DollarRange = tuple[int, int, int, int]

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


def inline_code_ranges(text: str) -> tuple[OffsetRange, ...]:
    ranges: list[OffsetRange] = []
    index = 0
    while index < len(text):
        if text[index] != "`":
            index += 1
            continue
        opener_end = _backtick_run_end(text, index)
        delimiter_length = opener_end - index
        close_start = _matching_backtick_run(text, opener_end, delimiter_length)
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
    for index in range(opener_index + 1, len(lines)):
        if is_fence_closer(lines[index][2], marker):
            return index
    return None


def _backtick_run_end(text: str, start: int) -> int:
    end = start
    while end < len(text) and text[end] == "`":
        end += 1
    return end


def _matching_backtick_run(text: str, start: int, length: int) -> int | None:
    index = start
    while index < len(text):
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
