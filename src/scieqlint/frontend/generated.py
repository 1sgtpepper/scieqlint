"""Generated-formula source facts for conservative Markdown input."""

from __future__ import annotations

import re
from collections.abc import Sequence

from scieqlint.facts.generated import GeneratedBracketDelimiter, GeneratedFormulaFact
from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.io.source import SourceDocument
from scieqlint.markdown import (
    _markdown_line_ownership_for_generated,  # pyright: ignore[reportPrivateUsage]
    is_escaped,
    without_tex_comments,
)
from scieqlint.source.maps import SourceMap

from .myst_shared import OffsetRange, line_ranges

# Semantic classification is owned by MathHost after candidate extraction.

_LATEX_ATOM_RE = re.compile(r"[A-Za-z]+")


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
        assert math_fact.document_id == document.path.as_posix()
        assert math_fact.span is not None
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
    """Record standalone generated LaTeX blocks outside owned containers."""

    facts: list[GeneratedFormulaFact] = []
    occupied = _merge_ranges(tuple(item for item in occupied if item[0] != item[1]))
    opener: int | None = None
    opener_container: tuple[int, ...] | None = None
    opener_kind: GeneratedBracketDelimiter | None = None
    opener_has_latex_signal = False
    closed_previous_line = False
    active_text = without_tex_comments(document.text)
    lines = line_ranges(document.text)
    ownership = _markdown_line_ownership_for_generated(document.text)
    occupied_cursor = _RangeCursor(occupied)
    for line_index, (line_start, line_end, _line) in enumerate(lines):
        recognized_close_previous_line = closed_previous_line
        closed_previous_line = False
        content_start, content, container_key, _block_start, _block_end = ownership[line_index]
        active_line = active_text[content_start : content_start + len(content)]
        stripped = active_line.strip(" \t")
        candidate_start = content_start + len(active_line) - len(active_line.lstrip(" \t"))
        line_is_occupied = occupied_cursor.overlaps(line_start, line_end)

        if opener is not None and (
            (line_is_occupied and "](" in active_line) or stripped.startswith("]:")
        ):
            # A multiline Markdown link owns its destination metadata, but its
            # label remains ordinary text. Reference-definition tails are likewise
            # not generated display closers.
            opener = None
            opener_container = None
            opener_kind = None
            opener_has_latex_signal = False

        if opener is not None and container_key != opener_container:
            assert opener_kind is not None
            _record_bracketed_block(
                facts,
                document,
                smap,
                opener,
                line_start,
                False,
                opener_kind,
                opener_has_latex_signal,
            )
            opener = None
            opener_container = None
            opener_kind = None
            opener_has_latex_signal = False

        if opener is not None and line_is_occupied:
            assert opener_kind is not None
            _record_bracketed_block(
                facts,
                document,
                smap,
                opener,
                line_start,
                False,
                opener_kind,
                opener_has_latex_signal,
            )
            opener = None
            opener_container = None
            opener_kind = None
            opener_has_latex_signal = False

        if (
            opener is not None
            and stripped
            and stripped not in {r"\]", "]"}
            and _is_text_item_start(ownership, line_index)
        ):
            assert opener_kind is not None
            _record_bracketed_block(
                facts,
                document,
                smap,
                opener,
                line_start,
                False,
                opener_kind,
                opener_has_latex_signal,
            )
            opener = None
            opener_container = None
            opener_kind = None
            opener_has_latex_signal = False

        if line_is_occupied:
            continue

        if opener is None:
            same_line_close = stripped.endswith(r"\]") and stripped != r"\]"
            close_start = content_start + active_line.rfind(r"\]")
            if same_line_close:
                same_line_close = not is_escaped(document.text, close_start)
            opener_is_standalone = (
                _is_text_item_start(ownership, line_index) or recognized_close_previous_line
            )
            if opener_is_standalone and stripped.startswith(r"\[") and same_line_close:
                close_offset = close_start + 2
                _record_bracketed_block(
                    facts,
                    document,
                    smap,
                    candidate_start,
                    close_offset,
                    True,
                    "escaped",
                    True,
                )
                closed_previous_line = True
            elif opener_is_standalone and stripped.startswith(r"\["):
                opener = candidate_start
                opener_container = container_key
                opener_kind = "escaped"
                opener_has_latex_signal = True
            elif opener_is_standalone and stripped == "[":
                opener = candidate_start
                opener_container = container_key
                opener_kind = "literal"
                opener_has_latex_signal = False
            continue

        assert opener_kind is not None
        if opener_kind == "literal":
            opener_has_latex_signal = opener_has_latex_signal or _contains_latex_signal(active_line)
        if stripped == (r"\]" if opener_kind == "escaped" else "]"):
            close_offset = candidate_start + (2 if opener_kind == "escaped" else 1)
            _record_bracketed_block(
                facts,
                document,
                smap,
                opener,
                close_offset,
                True,
                opener_kind,
                opener_has_latex_signal,
            )
            opener = None
            opener_container = None
            opener_kind = None
            opener_has_latex_signal = False
            closed_previous_line = True
        # A nested standalone opener remains content of the first block. This gives
        # the malformed input one deterministic owner and one EOF/close outcome.

    if opener is not None:
        assert opener_kind is not None
        _record_bracketed_block(
            facts,
            document,
            smap,
            opener,
            len(document.text),
            False,
            opener_kind,
            opener_has_latex_signal,
        )
    return tuple(facts)


def _contains_latex_signal(text: str) -> bool:
    """Recognize TeX or concise equation text without treating prose as math."""

    for index, character in enumerate(text):
        if (
            character == "\\"
            and not is_escaped(text, index)
            and index + 1 < len(text)
            and text[index + 1].isalpha()
        ):
            return True
    atoms = _LATEX_ATOM_RE.findall(text)
    return "=" in text and bool(atoms) and all(len(atom) <= 2 for atom in atoms)


def _record_bracketed_block(
    facts: list[GeneratedFormulaFact],
    document: SourceDocument,
    smap: SourceMap,
    start: int,
    end: int,
    complete: bool,
    delimiter_kind: GeneratedBracketDelimiter,
    has_latex_signal: bool,
) -> None:
    """Keep literal square wrappers quiet unless their body is TeX-looking."""

    if delimiter_kind == "literal" and not has_latex_signal:
        return
    facts.append(
        _bracketed_block_fact(
            document,
            smap,
            start,
            end,
            complete,
            delimiter_kind=delimiter_kind,
        )
    )


def _bracketed_block_fact(
    document: SourceDocument,
    smap: SourceMap,
    start: int,
    end: int,
    complete: bool,
    delimiter_kind: GeneratedBracketDelimiter,
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
        delimiter_kind=delimiter_kind,
    )


def _merge_ranges(ranges: Sequence[OffsetRange]) -> tuple[OffsetRange, ...]:
    merged: list[OffsetRange] = []
    for start, end in sorted(ranges):
        assert start < end
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return tuple(merged)


def _is_text_item_start(
    line_ownership: Sequence[tuple[int, str, tuple[int, ...], bool, bool]],
    index: int,
) -> bool:
    _content_start, _content, container_key, block_start, _block_end = line_ownership[index]
    if block_start or index == 0:
        return True
    (
        _previous_start,
        previous_content,
        previous_key,
        _previous_block_start,
        previous_block_end,
    ) = line_ownership[index - 1]
    return previous_key != container_key or not previous_content.strip(" \t") or previous_block_end


class _RangeCursor:
    """Sweep ordered ranges once for source-ordered overlap queries."""

    def __init__(self, ranges: Sequence[OffsetRange]) -> None:
        self._ranges = ranges
        self._index = 0

    def overlaps(self, start: int, end: int) -> bool:
        while self._index < len(self._ranges) and self._ranges[self._index][1] <= start:
            self._index += 1
        if self._index >= len(self._ranges):
            return False
        range_start, _range_end = self._ranges[self._index]
        return range_start < end
