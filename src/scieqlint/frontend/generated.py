"""Generated-formula source facts for conservative Markdown input."""

from __future__ import annotations

import re
from collections.abc import Sequence

from scieqlint.facts.generated import GeneratedFormulaFact
from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.io.source import SourceDocument
from scieqlint.markdown import MarkdownLinkToken
from scieqlint.source.maps import SourceMap

from .myst_shared import OffsetRange, in_ranges, line_ranges

# Semantic classification is owned by MathHost after candidate extraction.

_FORMULA_MARKER = "formula-not-decoded"
_FORMULA_MARKER_LINE_RE = re.compile(
    r"(?:formula-not-decoded|\[formula-not-decoded\]|<!--\s*formula-not-decoded\s*-->)"
)
_FORMULA_IMAGE_ALT_RE = re.compile(
    r"(?:formula|equation|math)(?:[ _-]*(?:image|placeholder|not[ _-]*decoded))?",
    re.IGNORECASE,
)
_FORMULA_IMAGE_NAME_RE = re.compile(
    r"(?:formula|equation|math)(?:[_-]*(?:\d+|placeholder|not[_-]*decoded))?"
    r"\.(?:avif|gif|jpe?g|png|svg|webp)",
    re.IGNORECASE,
)
_LIST_ITEM_RE = re.compile(r"^[ \t]*(?:[-+*]|\d+[.)])[ \t]+(?P<body>.*)$")
_BLOCKQUOTE_RE = re.compile(r"^[ \t]*>[ \t]?(?P<body>.*)$")
_ALPHA_WORD_RE = re.compile(r"(?<!\\)[A-Za-z]+")


def scan_formula_candidates(
    document: SourceDocument,
    inline_math: Sequence[InlineMathFact],
    display_math: Sequence[DisplayMathFact],
) -> tuple[GeneratedFormulaFact, ...]:
    """Emit one source-spanned candidate for each explicit math container."""

    source_math: tuple[InlineMathFact | DisplayMathFact, ...] = (
        *display_math,
        *(fact for fact in inline_math if fact.delimiter_kind != "plain-text"),
    )
    facts: list[GeneratedFormulaFact] = []
    for math_fact in source_math:
        if math_fact.document_id != document.path.as_posix() or math_fact.span is None:
            continue
        segment = document.text[math_fact.span.start : math_fact.span.end]
        facts.append(
            GeneratedFormulaFact(
                fact_id=(
                    f"{document.path.as_posix()}::generated-formula::candidate::"
                    f"{math_fact.span.start}"
                ),
                document_id=document.path.as_posix(),
                span=math_fact.span,
                raw=segment,
                confidence="source",
                kind="candidate",
                text=segment,
                candidate_kind="formula-text",
                source_math_fact_id=math_fact.fact_id,
            )
        )
    return tuple(
        sorted(
            facts,
            key=lambda fact: (fact.span.start if fact.span is not None else -1, fact.fact_id),
        )
    )


def scan_bracketed_latex_blocks(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
) -> tuple[GeneratedFormulaFact, ...]:
    """Record standalone ``\\[``/``\\]`` blocks outside owned containers."""

    facts: list[GeneratedFormulaFact] = []
    occupied = _merge_ranges(occupied)
    opener: int | None = None
    for line_start, _line_end, line in line_ranges(document.text):
        stripped = line.strip(" \t")
        content_start = line_start + len(line) - len(line.lstrip(" \t"))
        if in_ranges(content_start, occupied):
            continue

        if opener is None:
            same_line_close = stripped.endswith(r"\]") and stripped != r"\]"
            if stripped.startswith(r"\[") and same_line_close:
                close_offset = line_start + line.rfind(r"\]") + 2
                facts.append(
                    _bracketed_block_fact(document, smap, content_start, close_offset, True)
                )
            elif stripped == r"\[":
                opener = content_start
            continue

        if stripped == r"\]":
            close_offset = content_start + 2
            facts.append(_bracketed_block_fact(document, smap, opener, close_offset, True))
            opener = None
        # A nested standalone opener remains content of the first block. This gives
        # the malformed input one deterministic owner and one EOF/close outcome.

    if opener is not None:
        facts.append(_bracketed_block_fact(document, smap, opener, len(document.text), False))
    return tuple(facts)


def _bracketed_block_fact(
    document: SourceDocument,
    smap: SourceMap,
    start: int,
    end: int,
    complete: bool,
) -> GeneratedFormulaFact:
    text = document.text[start:end]
    return GeneratedFormulaFact(
        fact_id=f"{document.path.as_posix()}::generated-formula::bracketed-block::{start}",
        document_id=document.path.as_posix(),
        span=smap.span(start, end),
        raw=text,
        confidence="source",
        kind="candidate",
        text=text,
        candidate_kind="bracketed-block",
        complete=complete,
    )


def _merge_ranges(ranges: Sequence[OffsetRange]) -> tuple[OffsetRange, ...]:
    merged: list[OffsetRange] = []
    for start, end in sorted(ranges):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return tuple(merged)


def scan_formula_placeholders(
    document: SourceDocument,
    smap: SourceMap,
    inline_math: Sequence[InlineMathFact],
    display_math: Sequence[DisplayMathFact],
    dollar_ranges: Sequence[tuple[int, int, int, int]],
    links: Sequence[MarkdownLinkToken],
    opaque: Sequence[OffsetRange],
    code: Sequence[OffsetRange],
) -> tuple[GeneratedFormulaFact, ...]:
    """Record explicit generated formula placeholders without guessing repairs."""

    facts: list[GeneratedFormulaFact] = []
    occupied: list[OffsetRange] = []
    source_math: tuple[InlineMathFact | DisplayMathFact, ...] = (
        *display_math,
        *(fact for fact in inline_math if fact.delimiter_kind != "plain-text"),
    )
    for math_fact in source_math:
        if math_fact.document_id != document.path.as_posix() or math_fact.span is None:
            continue
        if math_fact.body.strip() != _FORMULA_MARKER:
            continue
        facts.append(
            _placeholder_fact(
                document,
                smap,
                math_fact.span.start,
                math_fact.span.end,
                _FORMULA_MARKER,
                source_math_fact_id=math_fact.fact_id,
            )
        )
        occupied.append((math_fact.span.start, math_fact.span.end))

    code = _merge_ranges(code)
    opaque = _merge_ranges(opaque)
    for line_start, _line_end, line in line_ranges(document.text):
        stripped = line.strip(" \t")
        match = _FORMULA_MARKER_LINE_RE.fullmatch(stripped)
        if match is None:
            if (
                stripped == "$$$$"
                and not in_ranges(line_start, code)
                and not in_ranges(line_start, opaque)
            ):
                start = line_start + len(line) - len(line.lstrip(" \t"))
                facts.append(
                    _placeholder_fact(
                        document,
                        smap,
                        start,
                        start + 4,
                        "empty-display-math",
                        complete=True,
                    )
                )
                occupied.append((start, start + 4))
            continue
        start = line_start + line.find(stripped)
        end = start + len(stripped)
        if _overlaps(start, end, occupied) or in_ranges(start, code):
            continue
        is_marker_comment = stripped.startswith("<!--")
        if in_ranges(start, opaque) and not is_marker_comment:
            continue
        facts.append(
            _placeholder_fact(
                document,
                smap,
                start,
                end,
                _FORMULA_MARKER,
            )
        )
        occupied.append((start, end))

    for start, body_start, body_end, close_end in dollar_ranges:
        if document.text[body_start:body_end].strip():
            continue
        if _overlaps(start, close_end, occupied):
            continue
        facts.append(
            _placeholder_fact(
                document,
                smap,
                start,
                close_end,
                "empty-display-math",
                complete=True,
            )
        )
        occupied.append((start, close_end))

    for token in links:
        if not token.is_image or token.destination is None or in_ranges(token.start, code):
            continue
        if token.image_alt is None or not _is_standalone_line(
            document.text, token.start, token.end
        ):
            continue
        alt = token.image_alt.strip()
        destination = token.destination.strip()
        filename = destination.rsplit("/", 1)[-1]
        if _FORMULA_IMAGE_ALT_RE.fullmatch(alt) is None and not (
            not alt and _FORMULA_IMAGE_NAME_RE.fullmatch(filename) is not None
        ):
            continue
        facts.append(
            _placeholder_fact(
                document,
                smap,
                token.start,
                token.end,
                "formula-image",
            )
        )

    return tuple(
        sorted(
            facts,
            key=lambda fact: (fact.span.start if fact.span is not None else -1, fact.fact_id),
        )
    )


def _placeholder_fact(
    document: SourceDocument,
    smap: SourceMap,
    start: int,
    end: int,
    placeholder_kind: str,
    *,
    source_math_fact_id: str | None = None,
    complete: bool | None = None,
) -> GeneratedFormulaFact:
    text = document.text[start:end]
    return GeneratedFormulaFact(
        fact_id=f"{document.path.as_posix()}::generated-formula::{placeholder_kind}::{start}",
        document_id=document.path.as_posix(),
        span=smap.span(start, end),
        raw=text,
        confidence="source",
        kind="candidate",
        text=text,
        candidate_kind="placeholder",
        source_math_fact_id=source_math_fact_id,
        placeholder_kind=placeholder_kind,
        complete=complete,
    )


def _overlaps(start: int, end: int, ranges: Sequence[OffsetRange]) -> bool:
    return any(start < range_end and range_start < end for range_start, range_end in ranges)


def _is_standalone_line(text: str, start: int, end: int) -> bool:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].strip(" \t") == text[start:end]


def scan_equation_like_text_items(
    document: SourceDocument,
    smap: SourceMap,
    inline_math: Sequence[InlineMathFact],
    occupied: Sequence[OffsetRange],
) -> tuple[GeneratedFormulaFact, ...]:
    """Classify whole isolated text items, never equation substrings in prose."""

    lines = line_ranges(document.text)
    occupied = _merge_ranges(occupied)
    facts: list[GeneratedFormulaFact] = []
    for math_fact in inline_math:
        if (
            math_fact.document_id != document.path.as_posix()
            or math_fact.delimiter_kind != "plain-text"
            or math_fact.span is None
            or in_ranges(math_fact.span.start, occupied)
        ):
            continue
        line_index = math_fact.span.line - 1
        if not 0 <= line_index < len(lines):
            continue
        line_start, _line_end, line = lines[line_index]
        content = _text_item_content(line, math_fact.surrounding_text_role)
        if content is None:
            continue
        content_offset, text = content
        start = line_start + content_offset
        end = start + len(text)
        if (
            start != math_fact.span.start
            or end != math_fact.span.end
            or text != math_fact.body
            or not _is_isolated_text_item(lines, line_index, math_fact.surrounding_text_role)
            or not _has_high_confidence_math_signal(text)
        ):
            continue
        facts.append(
            GeneratedFormulaFact(
                fact_id=(
                    f"{document.path.as_posix()}::generated-formula::equation-like-text::{start}"
                ),
                document_id=document.path.as_posix(),
                span=smap.span(start, end),
                raw=text,
                confidence="inferred",
                kind="equation-like-text",
                text=text,
                source_math_fact_id=math_fact.fact_id,
            )
        )
    return tuple(facts)


def _text_item_content(line: str, role: str) -> tuple[int, str] | None:
    if role == "heading":
        return None
    if role == "list-item":
        match = _LIST_ITEM_RE.fullmatch(line)
        if match is None:
            return None
        body = match.group("body").strip(" \t")
        return match.start("body") + len(match.group("body")) - len(
            match.group("body").lstrip(" \t")
        ), body
    if role == "blockquote":
        match = _BLOCKQUOTE_RE.fullmatch(line)
        if match is None:
            return None
        body = match.group("body").strip(" \t")
        return match.start("body") + len(match.group("body")) - len(
            match.group("body").lstrip(" \t")
        ), body
    stripped = line.strip(" \t")
    return len(line) - len(line.lstrip(" \t")), stripped


def _is_isolated_text_item(
    lines: Sequence[tuple[int, int, str]],
    index: int,
    role: str,
) -> bool:
    previous = lines[index - 1][2] if index > 0 else ""
    following = lines[index + 1][2] if index + 1 < len(lines) else ""
    if role == "list-item":
        return _list_boundary(previous) and _list_boundary(following)
    if role == "blockquote":
        return not previous.lstrip().startswith(">") and not following.lstrip().startswith(">")
    return not previous.strip() and not following.strip()


def _list_boundary(line: str) -> bool:
    return not line.strip() or _LIST_ITEM_RE.fullmatch(line) is not None


def _has_high_confidence_math_signal(text: str) -> bool:
    if any(character.isdigit() for character in text):
        return True
    if any(character in text for character in r"\_^{}*/+()[]"):
        return True
    words = _ALPHA_WORD_RE.findall(text)
    return bool(words) and all(len(word) <= 3 for word in words)
