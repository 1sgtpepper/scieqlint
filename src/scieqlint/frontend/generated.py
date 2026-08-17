"""Generated-formula source facts for conservative Markdown input."""

from __future__ import annotations

from collections.abc import Sequence

from scieqlint.facts.generated import GeneratedFormulaFact
from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.io.source import SourceDocument
from scieqlint.source.maps import SourceMap

from .myst_shared import OffsetRange, in_ranges, line_ranges

# Semantic classification is owned by MathHost after candidate extraction.


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
        kind="bracketed-block",
        text=text,
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
