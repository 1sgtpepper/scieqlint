"""Math fact lowering for conservative MyST/Markdown input."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from scieqlint.facts.math import (
    DisplayMathFact,
    InlineDelimiter,
    InlineMathFact,
    InlineTextRole,
)
from scieqlint.facts.reference import EquationLabelFact
from scieqlint.facts.structure import FenceFact
from scieqlint.io.source import SourceDocument
from scieqlint.markdown import code_fence_ranges, inline_code_ranges, is_escaped
from scieqlint.source.maps import SourceMap

from .myst_blocks import directive_option_prefix_lines
from .myst_shared import (
    DOLLAR_TAIL_LABEL_RE,
    MYST_OPTION_RE,
    TEX_LABEL_RE,
    OffsetRange,
    dollar_display_ranges,
    dollar_inline_ranges,
    in_ranges,
    line_ranges,
    normalize_label,
)

_MYST_MATH_ROLE_RE = re.compile(r"\{math\}`(?P<body>[^`\r\n]+)`")
_LATEX_PAREN_RE = re.compile(r"(?<!\\)\\\((?P<body>.*?)(?<!\\)\\\)")
_MATH_ATOM = r"(?:[A-Za-z0-9_{}]+|\\[A-Za-z]+)"
# This expression only finds a lexical candidate. MathHost owns the
# parse-status decision for the resulting fact.
_PLAIN_TEXT_MATH_CANDIDATE_RE = re.compile(
    rf"(?<![\w$])(?P<body>{_MATH_ATOM}(?:[ \t]*[+\-*/^][ \t]*{_MATH_ATOM})*"
    rf"[ \t]*(?:=|<=|>=|<|>|≤|≥|→)[ \t]*{_MATH_ATOM}"
    rf"(?:[ \t]*[+\-*/^][ \t]*{_MATH_ATOM})*)(?![\w$])"
)
_REFERENCE_ROLE_RE = re.compile(r"\{(?:ref|eq|numref)\}`[^`\r\n]+`")
_LIST_PREFIX_RE = re.compile(r"^[ \t]*(?:[-+*]|\d+[.)])[ \t]+")
_HEADING_PREFIX_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+")


def math_occupied_ranges(
    display_math: Sequence[DisplayMathFact],
) -> tuple[OffsetRange, ...]:
    return tuple((fact.span.start, fact.span.end) for fact in display_math if fact.span is not None)


def scan_display_math(
    document: SourceDocument,
    smap: SourceMap,
    fences: Sequence[FenceFact],
    occupied: Sequence[OffsetRange],
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
    lexical_occupied: Sequence[OffsetRange] = (),
) -> Iterable[InlineMathFact]:
    facts: list[InlineMathFact] = []
    for start, body_start, body_end, end in dollar_inline_ranges(
        document.text,
        occupied,
    ):
        body = document.text[body_start:body_end]
        text = body.strip()
        if not text:
            continue
        span_start = body_start + len(body) - len(body.lstrip())
        span_end = body_start + len(body.rstrip())
        role = _surrounding_text_role(document.text, start)
        facts.append(
            InlineMathFact(
                fact_id=f"{document.path.as_posix()}::inline-math::{start}",
                document_id=document.path.as_posix(),
                span=smap.span(span_start, span_end),
                raw=document.text[start:end],
                body=text,
                delimiter_kind="dollar",
                context=role,
                surrounding_text_role=role,
            )
        )

    lexical_opaque = _merge_occupied(
        (
            *occupied,
            *lexical_occupied,
            *code_fence_ranges(document.text),
            *inline_code_ranges(document.text),
            *((match.start(), match.end()) for match in _REFERENCE_ROLE_RE.finditer(document.text)),
        )
    )
    facts.extend(
        _delimited_inline_facts(
            document,
            smap,
            _MYST_MATH_ROLE_RE,
            "myst-role",
            lexical_opaque,
        )
    )
    facts.extend(
        _delimited_inline_facts(
            document,
            smap,
            _LATEX_PAREN_RE,
            "latex-paren",
            lexical_opaque,
        )
    )

    math_ranges = tuple((fact.span.start, fact.span.end) for fact in facts if fact.span is not None)
    facts.extend(
        _plain_text_math_facts(
            document,
            smap,
            _merge_occupied((*lexical_opaque, *math_ranges)),
        )
    )
    yield from sorted(
        facts,
        key=lambda fact: (fact.span.start if fact.span is not None else -1, fact.fact_id),
    )


def _merge_occupied(ranges: Sequence[OffsetRange]) -> tuple[OffsetRange, ...]:
    merged: list[OffsetRange] = []
    for start, end in sorted(ranges):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return tuple(merged)


def _delimited_inline_facts(
    document: SourceDocument,
    smap: SourceMap,
    pattern: re.Pattern[str],
    delimiter_kind: InlineDelimiter,
    occupied: Sequence[OffsetRange],
) -> Iterable[InlineMathFact]:
    for match in pattern.finditer(document.text):
        if in_ranges(match.start(), occupied) or is_escaped(document.text, match.start()):
            continue
        body = match.group("body")
        text = body.strip()
        if not text:
            continue
        body_start = match.start("body") + len(body) - len(body.lstrip())
        body_end = match.start("body") + len(body.rstrip())
        role = _surrounding_text_role(document.text, match.start())
        yield InlineMathFact(
            fact_id=f"{document.path.as_posix()}::inline-math::{match.start()}",
            document_id=document.path.as_posix(),
            span=smap.span(body_start, body_end),
            raw=match.group(0),
            body=text,
            delimiter_kind=delimiter_kind,
            context=role,
            surrounding_text_role=role,
        )


def _plain_text_math_facts(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
) -> Iterable[InlineMathFact]:
    for line_start, _line_end, line in line_ranges(document.text):
        for match in _PLAIN_TEXT_MATH_CANDIDATE_RE.finditer(line):
            start = line_start + match.start("body")
            end = line_start + match.end("body")
            if in_ranges(start, occupied):
                continue
            body = match.group("body")
            role = _surrounding_text_role(document.text, start)
            yield InlineMathFact(
                fact_id=f"{document.path.as_posix()}::inline-math-leak::{start}",
                document_id=document.path.as_posix(),
                span=smap.span(start, end),
                raw=body,
                body=body,
                delimiter_kind="plain-text",
                context=role,
                surrounding_text_role=role,
                confidence="inferred",
            )


def _surrounding_text_role(text: str, offset: int) -> InlineTextRole:
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    if _HEADING_PREFIX_RE.match(line):
        return "heading"
    if _LIST_PREFIX_RE.match(line):
        return "list-item"
    if line.lstrip().startswith(">"):
        return "blockquote"
    return "paragraph"


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
    for start, body_start, body_end, _close_end in dollar_display_ranges(
        document.text,
        occupied,
    ):
        fact_id = f"{document.path.as_posix()}::display-math::{start}"
        body_text = document.text[body_start:body_end]
        body = body_text.strip()
        if not body:
            continue
        span_start = body_start + len(body_text) - len(body_text.lstrip())
        span_end = body_start + len(body_text.rstrip())
        label_facts = list(_tex_label_facts(document, smap, fact_id, body_start, body_text))
        label_facts.extend(_dollar_tail_label_facts(document, smap, fact_id, body_end))
        labels.extend(label_facts)
        display.append(
            DisplayMathFact(
                fact_id=fact_id,
                document_id=document.path.as_posix(),
                span=smap.span(span_start, span_end),
                raw=body,
                body=body,
                container="dollar-dollar",
                label_fact_ids=tuple(label.fact_id for label in label_facts),
            )
        )
    return tuple(display), tuple(labels)


def _tex_label_facts(
    document: SourceDocument,
    smap: SourceMap,
    fact_id: str,
    body_start: int,
    body_text: str,
) -> Iterable[EquationLabelFact]:
    for match in TEX_LABEL_RE.finditer(body_text):
        if is_escaped(body_text, match.start()):
            continue
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
    for line_start, _line_end, line in directive_option_prefix_lines(document, fence):
        match = MYST_OPTION_RE.match(line)
        if match is None:
            break
        if match.group("key") != "label":
            continue
        label = match.group("value").strip()
        label_start = line_start + match.start("value")
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
    leading = len(tail) - len(tail.lstrip(" \t"))
    trailing = len(tail.rstrip(" \t"))
    candidate = tail[leading:trailing]
    match = DOLLAR_TAIL_LABEL_RE.fullmatch(candidate)
    if match is None:
        return
    group_name = "brace" if match.group("brace") else "paren"
    label = match.group(group_name)
    assert label is not None
    label_start = tail_start + leading + match.start(group_name)
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
