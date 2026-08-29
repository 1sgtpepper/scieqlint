"""Inline and inferred plain-text math lowering for MyST/Markdown."""

from __future__ import annotations

import re
from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import replace

from scieqlint.facts.math import InlineDelimiter, InlineMathFact
from scieqlint.io.source import SourceDocument
from scieqlint.markdown import (
    MarkdownReferenceSnapshot,
    is_escaped,
)
from scieqlint.source.maps import SourceMap

from .myst_shared import (
    LineRange,
    OffsetRange,
    dollar_inline_ranges,
    in_ranges,
    inline_math_accessibility_id,
    line_ranges,
    merge_occupied,
)

_MYST_MATH_ROLE_RE = re.compile(r"\{math\}`(?P<body>[^`\r\n]+)`")
_PLAIN_TEXT_RELATIONS = "=<>≤≥→"
_PLAIN_TEXT_OPERATORS = "+-*/^"


def scan_inline_math(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
    reference_snapshot: MarkdownReferenceSnapshot,
) -> Iterable[InlineMathFact]:
    facts: list[InlineMathFact] = []
    lines = tuple(line_ranges(document.text))
    dollar_ranges = tuple(dollar_inline_ranges(document.text, occupied))
    dollar_occupied = tuple((start, end) for start, _body_start, _body_end, end in dollar_ranges)
    for start, body_start, body_end, end in dollar_ranges:
        body = document.text[body_start:body_end]
        text = body.strip()
        if not text:
            continue
        span_start = body_start + len(body) - len(body.lstrip())
        span_end = body_start + len(body.rstrip())
        role = reference_snapshot.text_role_at(start)
        facts.append(
            InlineMathFact(
                fact_id=f"{document.path.as_posix()}::inline-math::{start}",
                document_id=document.path.as_posix(),
                span=smap.span(span_start, span_end),
                raw=document.text[start:end],
                body=text,
                delimiter_kind="dollar",
                surrounding_text_role=role,
            )
        )

    explicit_opaque = merge_occupied(
        (
            *occupied,
            *reference_snapshot.non_math_opaque_ranges,
            *dollar_occupied,
        )
    )
    role_candidates = tuple(
        _delimited_inline_candidates(
            document,
            smap,
            _MYST_MATH_ROLE_RE,
            "myst-role",
            explicit_opaque,
            reference_snapshot,
        )
    )
    facts.extend(fact for fact, _owner_range in role_candidates)
    role_occupied = merge_occupied(
        (*explicit_opaque, *(owner_range for _fact, owner_range in role_candidates))
    )
    facts.extend(_latex_paren_facts(document, smap, role_occupied, lines, reference_snapshot))

    math_ranges = tuple((fact.span.start, fact.span.end) for fact in facts if fact.span is not None)
    # Link text accepts explicit inline markup, but inferred equation-like text in a
    # label remains prose. Link metadata is already part of ``explicit_opaque``.
    inferred_opaque = merge_occupied(
        (
            *explicit_opaque,
            *((token.start, token.end) for token in reference_snapshot.links),
            *math_ranges,
        )
    )
    facts.extend(
        _plain_text_math_facts(
            document,
            smap,
            inferred_opaque,
            lines,
            reference_snapshot,
        )
    )
    ordered = sorted(
        facts,
        key=lambda fact: (fact.span.start if fact.span is not None else -1, fact.fact_id),
    )
    yield from _with_accessibility_ids(document, ordered)


def _with_accessibility_ids(
    document: SourceDocument,
    facts: Sequence[InlineMathFact],
) -> Iterable[InlineMathFact]:
    """Assign source-owned IDs without coupling metadata to byte offsets."""

    occurrences: dict[tuple[str, str], int] = {}
    for fact in facts:
        if fact.delimiter_kind == "plain-text":
            yield fact
            continue
        identity = (fact.delimiter_kind, fact.body)
        occurrence = occurrences.get(identity, 0)
        occurrences[identity] = occurrence + 1
        yield replace(
            fact,
            accessibility_id=inline_math_accessibility_id(
                document.path.as_posix(),
                fact.delimiter_kind,
                fact.body,
                occurrence,
            ),
        )


def _delimited_inline_candidates(
    document: SourceDocument,
    smap: SourceMap,
    pattern: re.Pattern[str],
    delimiter_kind: InlineDelimiter,
    occupied: Sequence[OffsetRange],
    reference_snapshot: MarkdownReferenceSnapshot,
) -> Iterable[tuple[InlineMathFact, OffsetRange]]:
    for match in pattern.finditer(document.text):
        if overlaps_occupied(match.start(), match.end(), occupied) or is_escaped(
            document.text, match.start()
        ):
            continue
        body = match.group("body")
        text = body.strip()
        if not text:
            continue
        body_start = match.start("body") + len(body) - len(body.lstrip())
        body_end = match.start("body") + len(body.rstrip())
        role = reference_snapshot.text_role_at(match.start())
        yield (
            InlineMathFact(
                fact_id=f"{document.path.as_posix()}::inline-math::{match.start()}",
                document_id=document.path.as_posix(),
                span=smap.span(body_start, body_end),
                raw=match.group(0),
                body=text,
                delimiter_kind=delimiter_kind,
                surrounding_text_role=role,
            ),
            (match.start(), match.end()),
        )


def _latex_paren_facts(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
    lines: Sequence[LineRange],
    reference_snapshot: MarkdownReferenceSnapshot,
) -> Iterable[InlineMathFact]:
    text = document.text
    for line_start, _line_end, line in lines:
        opener: int | None = None
        for match in re.finditer(r"\\[()]|%", line):
            delimiter = match.group(0)
            offset = line_start + match.start()
            if in_ranges(offset, occupied) or is_escaped(text, offset):
                continue
            if opener is not None and overlaps_occupied(opener, offset, occupied):
                opener = None
            if delimiter == "%":
                if opener is not None:
                    break
                continue
            if delimiter == r"\(":
                if opener is None:
                    opener = offset
                continue
            if opener is None:
                continue
            close = offset
            body = text[opener + 2 : close]
            stripped = body.strip()
            if stripped:
                body_start = opener + 2 + len(body) - len(body.lstrip())
                body_end = opener + 2 + len(body.rstrip())
                yield InlineMathFact(
                    fact_id=f"{document.path.as_posix()}::inline-math::{opener}",
                    document_id=document.path.as_posix(),
                    span=smap.span(body_start, body_end),
                    raw=text[opener : close + 2],
                    body=stripped,
                    delimiter_kind="latex-paren",
                    surrounding_text_role=reference_snapshot.text_role_at(opener),
                )
            opener = None



def overlaps_occupied(
    start: int,
    end: int,
    occupied: Sequence[OffsetRange],
) -> bool:
    index = bisect_left(occupied, (start, -1))
    if index < len(occupied) and occupied[index][0] < end:
        return True
    return index > 0 and occupied[index - 1][1] > start


def _plain_text_math_facts(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
    lines: Sequence[LineRange],
    reference_snapshot: MarkdownReferenceSnapshot,
) -> Iterable[InlineMathFact]:
    for line_start, _line_end, line in lines:
        for candidate_start, candidate_end in plain_text_math_candidate_spans(line):
            start = line_start + candidate_start
            end = line_start + candidate_end
            if overlaps_occupied(start, end, occupied):
                continue
            body = line[candidate_start:candidate_end]
            role = reference_snapshot.text_role_at(start)
            yield InlineMathFact(
                fact_id=f"{document.path.as_posix()}::inline-math-leak::{start}",
                document_id=document.path.as_posix(),
                span=smap.span(start, end),
                raw=body,
                body=body,
                delimiter_kind="plain-text",
                surrounding_text_role=role,
                confidence="inferred",
            )


def plain_text_math_candidate_spans(line: str) -> Iterable[OffsetRange]:
    """Scan plain-text equation candidates once from left to right."""

    index = 0
    candidate_start: int | None = None
    candidate_has_command = False
    relation_seen = False
    expecting_operand = True
    unary_sign = False
    complete_end: int | None = None
    blocked_until_boundary = False
    while index < len(line):
        if line[index] in " \t":
            if unary_sign:
                # A separated unary sign is an incomplete candidate. Do not
                # publish the complete prefix that precedes it.
                if candidate_start is not None and (candidate_has_command or relation_seen):
                    blocked_until_boundary = True
                candidate_start = None
                candidate_has_command = False
                relation_seen = False
                expecting_operand = True
                unary_sign = False
                complete_end = None
            index += 1
            continue

        token = _plain_text_math_token_at(line, index)
        if blocked_until_boundary:
            if token is None:
                blocked_until_boundary = False
            index = index + 1 if token is None else token[1]
            continue

        if token is None:
            if (
                candidate_start is not None
                and complete_end is not None
                and not expecting_operand
                and _plain_text_candidate_has_boundaries(line, candidate_start, complete_end)
            ):
                yield candidate_start, complete_end
            candidate_start = None
            candidate_has_command = False
            relation_seen = False
            expecting_operand = True
            unary_sign = False
            complete_end = None
            index += 1
            continue

        kind, token_end = token
        if expecting_operand:
            if kind == "atom":
                if candidate_start is None:
                    candidate_start = index
                if line[index] == "\\":
                    candidate_has_command = True
                expecting_operand = False
                unary_sign = False
                if relation_seen:
                    complete_end = token_end
                index = token_end
                continue
            if kind == "operator" and line[index] in "+-" and not unary_sign:
                if candidate_start is None:
                    candidate_start = index
                unary_sign = True
                index = token_end
                continue
            if candidate_start is not None and (candidate_has_command or relation_seen):
                blocked_until_boundary = True
            candidate_start = None
            candidate_has_command = False
            relation_seen = False
            expecting_operand = True
            unary_sign = False
            complete_end = None
            index = token_end
            continue

        if kind == "operator":
            expecting_operand = True
            unary_sign = False
            index = token_end
            continue
        if kind == "relation":
            relation_seen = True
            expecting_operand = True
            unary_sign = False
            complete_end = None
            index = token_end
            continue

        # A subsequent atom without punctuation is an attached group. Keep the
        # whole ambiguous region opaque so a truncated prefix cannot become a
        # fact; punctuation is handled by the token-none branch above.
        if candidate_start is not None and (candidate_has_command or relation_seen):
            blocked_until_boundary = True
            index = token_end
            candidate_start = None
            candidate_has_command = False
            relation_seen = False
            expecting_operand = True
            unary_sign = False
            complete_end = None
            continue
        candidate_start = None
        candidate_has_command = False
        relation_seen = False
        expecting_operand = True
        unary_sign = False
        complete_end = None
        # Reprocess an atom after resetting so an independent candidate can
        # start at the same token.

    if (
        candidate_start is not None
        and complete_end is not None
        and not expecting_operand
        and not blocked_until_boundary
        and _plain_text_candidate_has_boundaries(line, candidate_start, complete_end)
    ):
        yield candidate_start, complete_end


def _plain_text_math_token_at(line: str, index: int) -> tuple[str, int] | None:
    character = line[index]
    if character in _PLAIN_TEXT_RELATIONS:
        end = index + 1
        if character in "<>" and end < len(line) and line[end] == "=":
            end += 1
        return "relation", end
    if character in _PLAIN_TEXT_OPERATORS:
        return "operator", index + 1
    if character == "\\":
        end = index + 1
        while end < len(line) and line[end].isascii() and line[end].isalpha():
            end += 1
        return ("atom", end) if end > index + 1 else None
    if character.isascii() and character.isdigit():
        end = index + 1
        while end < len(line) and line[end].isascii() and line[end].isdigit():
            end += 1
        if (
            end + 1 < len(line)
            and line[end] == "."
            and line[end + 1].isascii()
            and line[end + 1].isdigit()
        ):
            end += 2
            while end < len(line) and line[end].isascii() and line[end].isdigit():
                end += 1
        return "atom", end
    if (
        character == "."
        and index + 1 < len(line)
        and line[index + 1].isascii()
        and line[index + 1].isdigit()
    ):
        end = index + 2
        while end < len(line) and line[end].isascii() and line[end].isdigit():
            end += 1
        return "atom", end
    if (character.isascii() and character.isalpha()) or character in "_{}":
        end = index + 1
        while end < len(line) and (
            (line[end].isascii() and line[end].isalnum()) or line[end] in "_{}"
        ):
            end += 1
        if end < len(line) and line[end] == "(":
            close = end + 1
            while close < len(line) and line[close] not in "()\r\n":
                close += 1
            if close < len(line) and line[close] == ")":
                end = close + 1
        return "atom", end
    return None


def _plain_text_candidate_has_boundaries(line: str, start: int, end: int) -> bool:
    if start > 0 and (line[start - 1].isalnum() or line[start - 1] in "_$."):
        return False
    if end >= len(line):
        return True
    if line[end] in "([{)]}":
        return False
    delimiter_end = end
    while delimiter_end < len(line) and line[delimiter_end] in " \t":
        delimiter_end += 1
    if delimiter_end < len(line) and line[delimiter_end] in "([{)]}":
        return False
    if line[end].isalnum() or line[end] in "_$":
        return False
    return not (line[end] == "." and end + 1 < len(line) and line[end + 1].isdigit())
