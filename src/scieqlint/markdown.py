"""Shared ordered lexical semantics for Markdown opaque regions and math."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

OffsetRange = tuple[int, int]
DollarRange = tuple[int, int, int, int]

_FENCE_OPENER_RE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
HTML_COMMENT_RE = re.compile(r"<!--.*?(?:-->|$)", re.DOTALL)
HTML_DECLARATION_RE = re.compile(r"<![A-Z][^>]*?(?:>|$)", re.IGNORECASE | re.DOTALL)
HTML_PROCESSING_INSTRUCTION_RE = re.compile(r"<\?.*?(?:\?>|$)", re.DOTALL)
HTML_CDATA_RE = re.compile(r"<!\[CDATA\[.*?(?:\]\]>|$)", re.DOTALL)
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
_MYST_ROLE_RE = re.compile(r"\{(?:ref|eq|numref)\}`[^`\n]+`")


@dataclass(frozen=True, slots=True)
class _LexicalRanges:
    fences: tuple[OffsetRange, ...]
    html: tuple[OffsetRange, ...]
    code: tuple[OffsetRange, ...]
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


def code_fence_ranges(text: str) -> tuple[OffsetRange, ...]:
    return _ordered_lexical_ranges(text, ()).fences


def markdown_opaque_ranges(text: str) -> tuple[OffsetRange, ...]:
    """Return source ranges whose contents cannot introduce Markdown structure."""

    lexical = _ordered_lexical_ranges(text, ())
    closed_display_starts = {start for start, _body_start, _body_end, _end in lexical.display}
    math_ranges = [
        (start, end) for start, _body_start, _body_end, end in (*lexical.display, *lexical.inline)
    ]
    math_ranges.extend(
        (start, len(text))
        for start in lexical.display_openers
        if start not in closed_display_starts
    )
    return _merge_ranges((*lexical.fences, *lexical.html, *lexical.code, *math_ranges))


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


def _merge_ranges(ranges: Sequence[OffsetRange]) -> tuple[OffsetRange, ...]:
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
        return _LexicalRanges((), (), (), (), (), ())

    fences: list[OffsetRange] = []
    html: list[OffsetRange] = []
    code: list[OffsetRange] = []
    display: list[DollarRange] = []
    inline: list[DollarRange] = []
    display_openers: list[int] = []
    occupied_cursor = _RangeCursor(occupied)
    backtick_runs = _backtick_runs(text)
    next_same_backtick = _next_same_backtick_runs(backtick_runs)
    backtick_index = 0
    line_index = 0
    index = 0

    while index < len(text):
        while backtick_index < len(backtick_runs) and backtick_runs[backtick_index][0] < index:
            backtick_index += 1
        while line_index + 1 < len(lines) and index >= lines[line_index][1]:
            line_index += 1
        line_start, _line_end, line = lines[line_index]
        line_content_end = line_start + len(line.rstrip("\r\n"))

        occupied_end = occupied_cursor.end_at(index)
        if occupied_end is not None:
            index = occupied_end
            continue

        if index == line_start:
            opener = parse_fence_opener(line)
            if opener is not None:
                marker, _info = opener
                close_index = _fence_close_index(lines, line_index, marker)
                range_end = lines[close_index][1] if close_index is not None else len(text)
                fences.append((line_start, range_end))
                index = range_end
                continue

        if text[index] == "{":
            role_end = _myst_role_end_at(text, index)
            if role_end is not None:
                index = role_end
                continue

        if text[index] == "<" and not is_escaped(text, index):
            html_end = _html_range_at(text, index)
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
        run_start, run_end, _delimiter_length = backtick_runs[backtick_index]
        if run_start != index:
            index += 1
            continue
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
        code=_merge_ranges(code),
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
    if start < len(text) or (not lines and text):
        lines.append((start, len(text), text[start:]))
    return lines


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
        if label_start == -1 or label_start + 2 >= content_end - 1 or any(
            char == "}" or char.isspace() for char in text[label_start + 2 : content_end - 1]
        ):
            label_start = content_end
    elif content_end > start and text[content_end - 1] == ")":
        label_start = text.rfind("(", start, content_end)
        if label_start == -1 or label_start + 1 >= content_end - 1 or any(
            char in "()" or char.isspace() for char in text[label_start + 1 : content_end - 1]
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
    if candidate + 2 < len(text) and text[candidate + 2] == "$":
        return -1
    return candidate


def _myst_role_end_at(text: str, start: int) -> int | None:
    if is_escaped(text, start):
        return None
    match = _MYST_ROLE_RE.match(text, start)
    return match.end() if match is not None else None


def _html_range_at(text: str, start: int) -> int | None:
    for pattern in (
        HTML_COMMENT_RE,
        HTML_DECLARATION_RE,
        HTML_PROCESSING_INSTRUCTION_RE,
        HTML_CDATA_RE,
    ):
        match = pattern.match(text, start)
        if match is not None:
            return match.end()

    block = HTML_BLOCK_OPEN_RE.match(text, start)
    if block is not None:
        tag = block.group("tag").lower()
        tag_start = text.find("<", start, block.end())
        assert tag_start != -1
        closing = _matching_html_block_close(text, tag_start, tag)
        if closing is not None:
            return closing
        if tag in HTML_RAWTEXT_TAGS:
            return len(text)
        blank_line = re.search(r"\n[ \t]*\n", text[block.end() :])
        return len(text) if blank_line is None else block.end() + blank_line.start() + 1

    tag = HTML_TAG_RE.match(text, start)
    return tag.end() if tag is not None else None


def _matching_html_block_close(text: str, start: int, tag: str) -> int | None:
    opener = HTML_TAG_RE.match(text, start)
    search_start = opener.end() if opener is not None else start + 1
    closing_pattern = re.compile(
        rf"</[ \t]*{re.escape(tag)}[ \t]*>",
        re.IGNORECASE,
    )
    if tag in HTML_RAWTEXT_TAGS:
        closing = closing_pattern.search(text, search_start)
        return closing.end() if closing is not None else None

    tag_pattern = re.compile(
        rf"<(?P<closing>/[ \t]*)?{re.escape(tag)}(?=[ \t/>])[^>]*>",
        re.IGNORECASE,
    )
    depth = 1
    for match in tag_pattern.finditer(text, search_start):
        if match.group("closing") is not None:
            depth -= 1
            if depth == 0:
                return match.end()
        elif not match.group().rstrip().endswith("/>"):
            depth += 1
    return None


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
