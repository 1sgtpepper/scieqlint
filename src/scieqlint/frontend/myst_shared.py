"""Shared lexical helpers for conservative MyST/Markdown lowering."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from scieqlint.io.source import SourceDocument
from scieqlint.markdown import (
    dollar_display_ranges as _dollar_display_ranges,
)
from scieqlint.markdown import (
    dollar_inline_ranges as _dollar_inline_ranges,
)
from scieqlint.markdown import (
    inline_code_ranges as _inline_code_ranges,
)

LineRange = tuple[int, int, str]
OffsetRange = tuple[int, int]

HEADING_RE = re.compile(r"^[ \t]{0,3}(?P<hashes>#{1,6})(?!#)(?P<space>[ \t]+)?(?P<body>.*)$")
ANCHOR_RE = re.compile(r"^[ \t]*\((?P<label>[^()\s]+)\)=[ \t]*$")
MD_LINK_RE = re.compile(r"\[[^\]]*]\(#(?P<target>[^)\s]+)\)")
ROLE_RE = re.compile(r"\{(?P<role>ref|eq|numref)}`(?P<body>[^`]+)`")
HTML_COMMENT_RE = re.compile(r"<!--.*?(?:-->|$)", re.DOTALL)
HTML_ELEMENT_RE = re.compile(
    r"<(?P<tag>[A-Za-z][A-Za-z0-9:-]*)\b[^>]*>.*?</(?P=tag)[ \t]*>",
    re.IGNORECASE | re.DOTALL,
)
HTML_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9:-]*(?:\s+[^<>]*?)?/?>", re.IGNORECASE)
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


@dataclass(frozen=True, slots=True)
class MarkdownLinkToken:
    start: int
    end: int
    destination_start: int
    destination_end: int
    is_image: bool


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


def markdown_link_tokens(text: str) -> tuple[MarkdownLinkToken, ...]:
    tokens: list[MarkdownLinkToken] = []
    index = 0
    while index < len(text):
        is_image = text[index] == "!" and index + 1 < len(text) and text[index + 1] == "["
        label_start = index + 1 if is_image else index
        if (
            (is_image or text[index] == "[")
            and not is_escaped(text, index)
            and (not is_image or not is_escaped(text, label_start))
        ):
            token = _parse_markdown_link(text, label_start, is_image)
            if token is not None:
                tokens.append(token)
                index = token.end
                continue
        index += 1
    return tuple(tokens)


def markdown_link_metadata_ranges(text: str) -> tuple[OffsetRange, ...]:
    return tuple(
        (token.start, token.end) if token.is_image else (token.destination_start, token.end)
        for token in markdown_link_tokens(text)
    )


def is_escaped(text: str, index: int) -> bool:
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return slash_count % 2 == 1


def _parse_markdown_link(
    text: str,
    label_start: int,
    is_image: bool,
) -> MarkdownLinkToken | None:
    label_end = _find_link_label_end(text, label_start)
    if label_end is None or label_end + 1 >= len(text) or text[label_end + 1] != "(":
        return None
    body = _parse_link_body(text, label_end + 2)
    if body is None:
        return None
    destination_start, destination_end, end = body
    return MarkdownLinkToken(
        start=label_start - 1 if is_image else label_start,
        end=end,
        destination_start=destination_start,
        destination_end=destination_end,
        is_image=is_image,
    )


def _find_link_label_end(text: str, start: int) -> int | None:
    depth = 1
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "\n":
            return None
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _parse_link_body(text: str, start: int) -> tuple[int, int, int] | None:
    index = _skip_link_whitespace(text, start)
    if index < len(text) and text[index] == "<":
        destination_start = index + 1
        index += 1
        while index < len(text):
            if text[index] == "\\":
                index += 2
                continue
            if text[index] == ">":
                destination_end = index
                index += 1
                break
            if text[index] in "\n\r":
                return None
            index += 1
        else:
            return None
    else:
        destination_start = index
        depth = 0
        while index < len(text):
            char = text[index]
            if char == "\\":
                index += 2
                continue
            if char in " \t\n\r" and depth == 0:
                break
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            index += 1
        if depth != 0:
            return None
        destination_end = index

    index = _skip_link_whitespace(text, index)
    if index >= len(text):
        return None
    if text[index] != ")":
        index = _parse_link_title(text, index)
        if index is None:
            return None
        index = _skip_link_whitespace(text, index)
        if index >= len(text) or text[index] != ")":
            return None
    return destination_start, destination_end, index + 1


def _parse_link_title(text: str, start: int) -> int | None:
    opener = text[start]
    if opener in {'"', "'"}:
        index = start + 1
        while index < len(text):
            if text[index] == "\\":
                index += 2
                continue
            if text[index] == opener:
                return index + 1
            if text[index] in "\n\r":
                return None
            index += 1
        return None
    if opener != "(":
        return None
    depth = 1
    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


def _skip_link_whitespace(text: str, start: int) -> int:
    while start < len(text) and text[start] in " \t\n\r":
        start += 1
    return start


def inline_code_ranges(document: SourceDocument) -> tuple[OffsetRange, ...]:
    return _inline_code_ranges(document.text)


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


def opaque_markdown_ranges(
    text: str,
    occupied: Sequence[OffsetRange],
) -> tuple[OffsetRange, ...]:
    ranges = [*occupied, *_inline_code_ranges(text), *_code_fence_ranges(text)]
    ranges.extend(
        (start, close_end)
        for start, _body_start, _body_end, close_end in _dollar_display_ranges(text, ranges)
        if not in_ranges(start, ranges)
    )
    ranges.extend(
        (start, close_end)
        for start, _body_start, _body_end, close_end in _dollar_inline_ranges(text, ranges)
        if not in_ranges(start, ranges)
    )
    ranges.extend((match.start(), match.end()) for match in HTML_COMMENT_RE.finditer(text))
    ranges.extend((match.start(), match.end()) for match in HTML_ELEMENT_RE.finditer(text))
    ranges.extend((match.start(), match.end()) for match in HTML_TAG_RE.finditer(text))
    return tuple(ranges)


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
