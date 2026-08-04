"""Shared lexical helpers for conservative MyST/Markdown lowering."""

from __future__ import annotations

import re
from collections.abc import Sequence

from scieqlint.io.source import SourceDocument

LineRange = tuple[int, int, str]
OffsetRange = tuple[int, int]

HEADING_RE = re.compile(r"^[ \t]{0,3}(?P<hashes>#{1,6})(?!#)(?P<space>[ \t]+)?(?P<body>.*)$")
ANCHOR_RE = re.compile(r"^[ \t]*\((?P<label>[^()\s]+)\)=[ \t]*$")
FENCE_RE = re.compile(r"^(?P<indent>[ \t]{0,3})(?P<marker>`{3,}|~{3,})(?P<info>[^\n]*)$")
MD_LINK_RE = re.compile(r"\[[^\]]*]\(#(?P<target>[^)\s]+)\)")
ROLE_RE = re.compile(r"\{(?P<role>ref|eq|numref)}`(?P<body>[^`]+)`")
INLINE_CODE_RE = re.compile(r"(?P<ticks>`+)[^`\n]*(?P=ticks)")
TEX_LABEL_RE = re.compile(r"\\label\{(?P<label>[^{}]+)\}")
DOLLAR_TAIL_LABEL_RE = re.compile(r"\{#(?P<brace>[^}\s]+)\}|\((?P<paren>[^()\s]+)\)")
DIRECTIVE_INFO_RE = re.compile(r"^\{(?P<name>[^}\s]+)\}(?P<arg>.*)$")
ROLE_MARKER_RE = re.compile(r"\{(?P<role>ref|eq|numref)\}")
QUARTO_OPTION_RE = re.compile(r"^[ \t]*#\|[ \t]*(?P<key>[A-Za-z0-9_.-]+):[ \t]*(?P<value>.*)$")
MYST_OPTION_RE = re.compile(
    r"^[ \t]*:(?P<key>[A-Za-z0-9_.-]+):[ \t]*(?P<value>.*)$",
    re.MULTILINE,
)
CODE_CELL_TAG_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def line_ranges(text: str) -> tuple[LineRange, ...]:
    ranges: list[LineRange] = []
    start = 0
    for line in text.splitlines(keepends=True):
        end = start + len(line)
        ranges.append((start, end, line[:-1] if line.endswith("\n") else line))
        start = end
    return tuple(ranges)


def in_ranges(position: int, ranges: Sequence[OffsetRange]) -> bool:
    return any(start <= position < end for start, end in ranges)


def inline_code_ranges(document: SourceDocument) -> tuple[OffsetRange, ...]:
    return tuple((match.start(), match.end()) for match in INLINE_CODE_RE.finditer(document.text))


def dollar_display_ranges(
    text: str,
    occupied: Sequence[OffsetRange],
) -> tuple[tuple[int, int, int, int], ...]:
    ranges: list[tuple[int, int, int, int]] = []
    cursor = 0
    while True:
        start = text.find("$$", cursor)
        if start == -1:
            break
        if (
            in_ranges(start, occupied)
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


def dollar_inline_ranges(
    text: str,
    occupied: Sequence[OffsetRange],
) -> tuple[tuple[int, int, int, int], ...]:
    ranges: list[tuple[int, int, int, int]] = []
    cursor = 0
    while True:
        start = text.find("$", cursor)
        if start == -1:
            break
        if (
            in_ranges(start, occupied)
            or is_escaped(text, start)
            or _is_adjacent_to_dollar(text, start)
        ):
            cursor = start + 1
            continue

        candidate = start + 1
        found = False
        while True:
            close = text.find("$", candidate)
            if close == -1 or "\n" in text[start + 1 : close]:
                break
            if (
                not in_ranges(close, occupied)
                and not is_escaped(text, close)
                and not _is_adjacent_to_dollar(text, close)
            ):
                if close > start + 1:
                    ranges.append((start, start + 1, close, close + 1))
                    cursor = close + 1
                    found = True
                break
            candidate = close + 1
        if not found:
            cursor = start + 1
    return tuple(ranges)


def is_escaped(text: str, index: int) -> bool:
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return slash_count % 2 == 1


def _is_display_opener(text: str, start: int) -> bool:
    line_start = text.rfind("\n", 0, start) + 1
    prefix = text[line_start:start]
    return prefix == prefix.lstrip(" ") and len(prefix) <= 3


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
        if not in_ranges(close, occupied) and not is_escaped(text, close):
            return close
        cursor = close + 2


def _is_adjacent_to_dollar(text: str, index: int) -> bool:
    return (
        (index > 0 and text[index - 1] == "$")
        or (index + 1 < len(text) and text[index + 1] == "$")
    )


def extract_role_target_and_title(body: str) -> tuple[str, str | None]:
    angle = re.search(r"<([^<>]+)>\s*$", body)
    if angle is not None:
        title = body[: angle.start()].strip() or None
        return angle.group(1).strip(), title
    return body.strip(), None


def normalize_label(value: str) -> str:
    value = value.strip()
    if value.startswith("#"):
        value = value[1:]
    return value


def slug(text: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9 _.-]+", "", text).strip().lower()
    return re.sub(r"[\s_]+", "-", candidate)
