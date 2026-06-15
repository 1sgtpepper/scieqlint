"""Math fact lowering for conservative MyST/Markdown input."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.facts.reference import EquationLabelFact
from scieqlint.facts.structure import FenceFact
from scieqlint.io.source import SourceDocument
from scieqlint.source.maps import SourceMap

from .myst_shared import (
    DOLLAR_TAIL_LABEL_RE,
    INLINE_MATH_RE,
    MYST_OPTION_RE,
    TEX_LABEL_RE,
    OffsetRange,
    in_ranges,
    inline_code_ranges,
    normalize_label,
)


def math_occupied_ranges(
    fence_ranges: Sequence[OffsetRange],
    display_math: Sequence[DisplayMathFact],
) -> tuple[OffsetRange, ...]:
    math_ranges = tuple(
        (fact.span.start, fact.span.end) for fact in display_math if fact.span is not None
    )
    return (*tuple(fence_ranges), *math_ranges)


def scan_display_math(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
    fences: Sequence[FenceFact],
) -> tuple[tuple[DisplayMathFact, ...], tuple[EquationLabelFact, ...]]:
    display: list[DisplayMathFact] = []
    labels: list[EquationLabelFact] = []
    for fence in fences:
        if fence.kind != "math" or fence.body_span is None:
            continue
        math_fact, label_facts = _math_fact_from_fence(document, smap, fence)
        display.append(math_fact)
        labels.extend(label_facts)

    dollar_display, dollar_labels = _dollar_display_math(document, smap, occupied)
    display.extend(dollar_display)
    labels.extend(dollar_labels)
    return tuple(display), tuple(labels)


def scan_inline_math(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
) -> Iterable[InlineMathFact]:
    occupied_with_code = (*tuple(occupied), *inline_code_ranges(document))
    for match in INLINE_MATH_RE.finditer(document.text):
        if in_ranges(match.start(), occupied_with_code):
            continue
        body = match.group("body")
        yield InlineMathFact(
            fact_id=f"{document.path.as_posix()}::inline-math::{match.start()}",
            document_id=document.path.as_posix(),
            span=smap.span(match.start("body"), match.end("body")),
            raw=match.group(0),
            body=body,
            delimiter_kind="dollar",
            context="paragraph",
        )


def _math_fact_from_fence(
    document: SourceDocument,
    smap: SourceMap,
    fence: FenceFact,
) -> tuple[DisplayMathFact, tuple[EquationLabelFact, ...]]:
    assert fence.body_span is not None
    body_text = document.text[fence.body_span.start : fence.body_span.end]
    body = body_text.strip()
    fact_id = f"{fence.fact_id}::math"
    labels = list(_tex_label_facts(document, smap, fact_id, fence.body_span.start, body_text))
    if fence.info_string == "{math}":
        labels.extend(_myst_math_label_facts(document, smap, fact_id, fence))
    return (
        DisplayMathFact(
            fact_id=fact_id,
            document_id=fence.document_id,
            span=fence.body_span,
            raw=body,
            body=body,
            container="myst-math-directive" if fence.info_string == "{math}" else "fenced-math",
            label_fact_ids=tuple(label.fact_id for label in labels),
        ),
        tuple(labels),
    )


def _dollar_display_math(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
) -> tuple[tuple[DisplayMathFact, ...], tuple[EquationLabelFact, ...]]:
    display: list[DisplayMathFact] = []
    labels: list[EquationLabelFact] = []
    cursor = 0
    while True:
        start = document.text.find("$$", cursor)
        if start == -1:
            break
        if in_ranges(start, occupied):
            cursor = start + 2
            continue
        close = _find_unoccupied_display_close(document.text, start + 2, occupied)
        if close == -1:
            cursor = start + 2
            continue
        fact_id = f"{document.path.as_posix()}::display-math::{start}"
        body_start = start + 2
        body_end = close
        body_text = document.text[body_start:body_end]
        label_facts = list(_tex_label_facts(document, smap, fact_id, body_start, body_text))
        label_facts.extend(_dollar_tail_label_facts(document, smap, fact_id, close))
        labels.extend(label_facts)
        display.append(
            DisplayMathFact(
                fact_id=fact_id,
                document_id=document.path.as_posix(),
                span=smap.span(body_start, body_end),
                raw=body_text.strip(),
                body=body_text.strip(),
                container="dollar-dollar",
                label_fact_ids=tuple(label.fact_id for label in label_facts),
            )
        )
        cursor = close + 2
    return tuple(display), tuple(labels)


def _find_unoccupied_display_close(
    text: str,
    start: int,
    occupied: Sequence[OffsetRange],
) -> int:
    cursor = start
    while True:
        close = text.find("$$", cursor)
        if close == -1:
            return -1
        if not in_ranges(close, occupied):
            return close
        cursor = close + 2


def _tex_label_facts(
    document: SourceDocument,
    smap: SourceMap,
    fact_id: str,
    body_start: int,
    body_text: str,
) -> Iterable[EquationLabelFact]:
    for match in TEX_LABEL_RE.finditer(body_text):
        label = match.group("label")
        label_start = body_start + match.start("label")
        yield EquationLabelFact(
            fact_id=f"{fact_id}::label::{label_start}",
            document_id=document.path.as_posix(),
            span=smap.span(label_start, label_start + len(label)),
            raw=label,
            label=label,
            normalized_label=normalize_label(label),
            label_syntax_kind="tex-label",
            source_block_id=fact_id,
            label_span=smap.span(label_start, label_start + len(label)),
        )


def _myst_math_label_facts(
    document: SourceDocument,
    smap: SourceMap,
    fact_id: str,
    fence: FenceFact,
) -> Iterable[EquationLabelFact]:
    assert fence.body_span is not None
    body_text = document.text[fence.body_span.start : fence.body_span.end]
    for match in MYST_OPTION_RE.finditer(body_text):
        if match.group("key") != "label":
            continue
        label = match.group("value").strip()
        label_start = fence.body_span.start + match.start("value")
        yield EquationLabelFact(
            fact_id=f"{fact_id}::label::{label_start}",
            document_id=document.path.as_posix(),
            span=smap.span(label_start, label_start + len(label)),
            raw=label,
            label=label,
            normalized_label=normalize_label(label),
            label_syntax_kind="myst-directive-option",
            source_block_id=fact_id,
            label_span=smap.span(label_start, label_start + len(label)),
        )


def _dollar_tail_label_facts(
    document: SourceDocument,
    smap: SourceMap,
    fact_id: str,
    close: int,
) -> Iterable[EquationLabelFact]:
    line_end = document.text.find("\n", close)
    if line_end == -1:
        line_end = len(document.text)
    tail_start = close + 2
    tail = document.text[tail_start:line_end]
    for match in DOLLAR_TAIL_LABEL_RE.finditer(tail):
        group_name = "brace" if match.group("brace") else "paren"
        label = match.group(group_name)
        assert label is not None
        label_start = tail_start + match.start(group_name)
        yield EquationLabelFact(
            fact_id=f"{fact_id}::label::{label_start}",
            document_id=document.path.as_posix(),
            span=smap.span(label_start, label_start + len(label)),
            raw=label,
            label=label,
            normalized_label=normalize_label(label),
            label_syntax_kind="dollar-tail",
            source_block_id=fact_id,
            label_span=smap.span(label_start, label_start + len(label)),
        )
