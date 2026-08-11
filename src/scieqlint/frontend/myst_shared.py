"""Shared lexical helpers for conservative MyST/Markdown lowering."""

from __future__ import annotations

import re
from collections.abc import Sequence

from scieqlint.markdown import (
    dollar_display_ranges as _dollar_display_ranges,
    dollar_inline_ranges as _dollar_inline_ranges,
)
from scieqlint.markdown import range_contains

LineRange = tuple[int, int, str]
OffsetRange = tuple[int, int]

HEADING_RE = re.compile(r"^[ \t]{0,3}(?P<hashes>#{1,6})(?!#)(?P<space>[ \t]+)?(?P<body>.*)$")
ANCHOR_RE = re.compile(r"^[ \t]*\((?P<label>[^()\s]+)\)=[ \t]*$")
ROLE_RE = re.compile(r"\{(?P<role>ref|eq|numref)}`(?P<body>[^`\r\n]+)`")
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
    return range_contains(position, ranges)


def dollar_display_ranges(
    text: str,
    occupied: Sequence[OffsetRange],
) -> tuple[tuple[int, int, int, int], ...]:
    return _dollar_display_ranges(text, occupied)


def dollar_inline_ranges(
    text: str,
    occupied: Sequence[OffsetRange],
) -> tuple[tuple[int, int, int, int], ...]:
    return _dollar_inline_ranges(text, occupied)


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
