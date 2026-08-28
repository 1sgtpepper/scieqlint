"""FrontendHost-owned JSON decoding and source-range primitives for notebooks."""

from __future__ import annotations

import json
from typing import cast

_MAX_JSON_INTEGER_DIGITS = 4096


def parse_json_document(text: str) -> tuple[object, tuple[int, int]]:
    """Decode one JSON document and retain the authoritative root range."""

    decoder = json_decoder()
    start = _skip_json_whitespace(text, 0)
    value, end = _decode_json_value(decoder, text, start)
    trailing = _skip_json_whitespace(text, end)
    if trailing != len(text):
        raise json.JSONDecodeError("Extra data", text, trailing)
    return value, (start, end)


def json_decoder() -> json.JSONDecoder:
    return json.JSONDecoder(
        parse_int=_parse_json_integer,
        parse_constant=_reject_json_constant,
    )


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON constant is not supported: {value}")


def _decode_json_value(
    decoder: json.JSONDecoder,
    text: str,
    start: int,
) -> tuple[object, int]:
    start = _skip_json_whitespace(text, start)
    if start >= len(text):
        raise json.JSONDecodeError("Expecting value", text, start)
    return decoder.raw_decode(text, start)


def _parse_json_integer(text: str) -> int:
    digits = text[1:] if text.startswith("-") else text
    if len(digits) > _MAX_JSON_INTEGER_DIGITS:
        raise ValueError(f"JSON integer exceeds {_MAX_JSON_INTEGER_DIGITS} digits")
    value = 0
    for digit in digits:
        value = value * 10 + ord(digit) - ord("0")
    return -value if text.startswith("-") else value


def json_object_members(
    decoder: json.JSONDecoder,
    text: str,
    start: int,
    end: int,
) -> dict[str, tuple[int, int]]:
    start = _skip_json_whitespace(text, start)
    position = _skip_json_whitespace(text, start + 1)
    members: dict[str, tuple[int, int]] = {}
    while position < end - 1:
        position = _skip_json_whitespace(text, position)
        key, key_end = _decode_json_value(decoder, text, position)
        position = _skip_json_whitespace(text, key_end)
        value_start = _skip_json_whitespace(text, position + 1)
        _, value_end = _decode_json_value(decoder, text, value_start)
        members[cast(str, key)] = (value_start, value_end)
        position = _skip_json_whitespace(text, value_end)
        if position < end - 1:
            position += 1
    return members


def json_array_ranges(
    decoder: json.JSONDecoder,
    text: str,
    start: int,
    end: int,
) -> tuple[tuple[int, int], ...]:
    start = _skip_json_whitespace(text, start)
    position = _skip_json_whitespace(text, start + 1)
    ranges: list[tuple[int, int]] = []
    while position < end - 1:
        position = _skip_json_whitespace(text, position)
        _, value_end = _decode_json_value(decoder, text, position)
        ranges.append((position, value_end))
        position = _skip_json_whitespace(text, value_end)
        if position < end - 1:
            position += 1
    return tuple(ranges)


def _skip_json_whitespace(text: str, start: int) -> int:
    while start < len(text) and text[start] in " \t\r\n":
        start += 1
    return start


def json_string_character_ranges(
    text: str,
    start: int,
    end: int,
) -> list[tuple[str, int, int]]:
    ranges: list[tuple[str, int, int]] = []
    position = start + 1
    while position < end - 1:
        raw_start = position
        if text[position] != "\\":
            ranges.append((text[position], raw_start, raw_start + 1))
            position += 1
            continue
        position += 1
        escape = text[position]
        if escape == "u":
            codepoint = int(text[position + 1 : position + 5], 16)
            raw_end = position + 5
            character = chr(codepoint)
            if (
                0xD800 <= codepoint <= 0xDBFF
                and raw_end + 5 < end
                and text[raw_end] == "\\"
                and text[raw_end + 1] == "u"
            ):
                low = int(text[raw_end + 2 : raw_end + 6], 16)
                if 0xDC00 <= low <= 0xDFFF:
                    character = chr(0x10000 + ((codepoint - 0xD800) << 10) + (low - 0xDC00))
                    raw_end += 6
            ranges.append((character, raw_start, raw_end))
            position = raw_end
            continue
        escaped = {
            '"': '"',
            "\\": "\\",
            "/": "/",
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
        }[escape]
        ranges.append((escaped, raw_start, position + 1))
        position += 1
    return ranges
