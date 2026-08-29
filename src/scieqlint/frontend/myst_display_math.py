"""Display and raw-LaTeX math lowering for MyST/Markdown."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from scieqlint.facts.math import DisplayMathFact
from scieqlint.facts.reference import EquationLabelFact, EquationRefFact
from scieqlint.facts.structure import FenceFact
from scieqlint.io.source import SourceDocument
from scieqlint.markdown import is_escaped, range_contains, scan_tex_lexically
from scieqlint.source.maps import SourceMap

from .myst_blocks import directive_option_prefix_lines
from .myst_shared import (
    DOLLAR_TAIL_LABEL_RE,
    MYST_OPTION_RE,
    TEX_LABEL_RE,
    OffsetRange,
    in_ranges,
    merge_occupied,
    normalize_label,
)

_TEX_REFERENCE_RE = re.compile(r"\\(?P<kind>eqref|ref)\{(?P<target>[^{}\r\n]+)\}")


def math_occupied_ranges(
    display_math: Sequence[DisplayMathFact],
) -> tuple[OffsetRange, ...]:
    return tuple(
        sorted((fact.span.start, fact.span.end) for fact in display_math if fact.span is not None)
    )


def scan_display_math(
    document: SourceDocument,
    smap: SourceMap,
    fences: Sequence[FenceFact],
    dollar_ranges: Sequence[tuple[int, int, int, int]],
    occupied: Sequence[OffsetRange] = (),
    fence_occupied: Sequence[OffsetRange] = (),
) -> tuple[
    tuple[DisplayMathFact, ...],
    tuple[EquationLabelFact, ...],
    tuple[EquationRefFact, ...],
]:
    display: list[DisplayMathFact] = []
    labels: list[EquationLabelFact] = []
    references: list[EquationRefFact] = []
    occupied = merge_occupied(occupied)
    fence_occupied = merge_occupied(fence_occupied)
    for fence in fences:
        if (
            fence.kind != "math"
            or fence.body_span is None
            or in_ranges(fence.opener_span.start, fence_occupied)
        ):
            continue
        math_fact, label_facts, reference_facts = _math_fact_from_fence(document, smap, fence)
        display.append(math_fact)
        labels.extend(label_facts)
        references.extend(reference_facts)

    dollar_display, dollar_labels, dollar_references = _dollar_display_math(
        document,
        smap,
        tuple(
            dollar_range
            for dollar_range in dollar_ranges
            if not in_ranges(dollar_range[0], occupied)
        ),
    )
    display.extend(dollar_display)
    labels.extend(dollar_labels)
    references.extend(dollar_references)
    return tuple(display), tuple(labels), tuple(references)


def scan_raw_latex_math(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
    bracketed_occupied: Sequence[OffsetRange] = (),
) -> tuple[
    tuple[DisplayMathFact, ...],
    tuple[EquationLabelFact, ...],
    tuple[EquationRefFact, ...],
]:
    """Lower top-level raw-LaTeX environment candidates without classifying them."""

    displays: list[DisplayMathFact] = []
    occupied_ranges = merge_occupied(occupied)
    bracketed_ranges = merge_occupied(bracketed_occupied)
    for environment, start, body_start, body_end, end, complete in _raw_math_environment_ranges(
        document.text, occupied_ranges, bracketed_ranges
    ):
        fact_id = f"{document.path.as_posix()}::raw-math::{start}"
        raw = document.text[start:end]
        body_text = document.text[body_start:body_end]
        display = DisplayMathFact(
            fact_id=fact_id,
            document_id=document.path.as_posix(),
            span=smap.span(start, end),
            raw=raw,
            body=body_text.strip(),
            container="raw-latex",
            environment=environment,
            complete=complete,
            source_syntax="raw-latex",
        )
        displays.append(display)
    # Raw environments are lexical candidates only. MathHost decides the final
    # classification and preserves parseable facts for complete non-opaque forms.
    return tuple(displays), (), ()


def _raw_math_environment_ranges(
    text: str,
    occupied: Sequence[OffsetRange],
    bracketed_occupied: Sequence[OffsetRange] = (),
) -> Iterable[tuple[str, int, int, int, int, bool]]:
    stack: list[tuple[str, int, int, bool]] = []
    candidate_malformed = False
    lexical = scan_tex_lexically(text, occupied=(*occupied, *bracketed_occupied))
    for kind, environment, token_start, token_end in lexical.environment_tokens:
        if not stack and (
            in_ranges(token_start, occupied) or in_ranges(token_start, bracketed_occupied)
        ):
            continue
        if kind == "begin":
            if not stack:
                candidate_malformed = False
            stack.append(
                (
                    environment,
                    token_start,
                    token_end,
                    not stack,
                )
            )
            continue
        if not stack:
            continue
        if stack[-1][0] != environment:
            candidate_malformed = True
            continue
        outer_environment, start, body_start, is_candidate = stack.pop()
        if stack or not is_candidate:
            continue
        yield (
            outer_environment,
            start,
            body_start,
            token_start,
            token_end,
            not candidate_malformed,
        )
        candidate_malformed = False
    if stack:
        outer_environment, start, body_start, _ = stack[0]
        yield (
            outer_environment,
            start,
            body_start,
            len(text),
            len(text),
            False,
        )


def _math_fact_from_fence(
    document: SourceDocument,
    smap: SourceMap,
    fence: FenceFact,
) -> tuple[
    DisplayMathFact,
    tuple[EquationLabelFact, ...],
    tuple[EquationRefFact, ...],
]:
    assert fence.body_span is not None
    body_text = document.text[fence.body_span.start : fence.body_span.end]
    body = body_text.strip()
    fact_id = f"{fence.fact_id}::math"
    labels: list[EquationLabelFact] = []
    references: tuple[EquationRefFact, ...] = ()
    if fence.is_closed:
        labels.extend(_tex_label_facts(document, smap, fact_id, fence.body_span.start, body_text))
        references = tuple(
            _tex_reference_facts(document, smap, fact_id, fence.body_span.start, body_text)
        )
        if fence.info_string == "{math}":
            labels.extend(_myst_math_label_facts(document, smap, fact_id, fence))
    return (
        DisplayMathFact(
            fact_id=fact_id,
            document_id=fence.document_id,
            span=fence.body_span,
            raw=body,
            body=body,
            container=("myst-math-directive" if fence.info_string == "{math}" else "fenced-math"),
            label_fact_ids=tuple(label.fact_id for label in labels),
            complete=fence.is_closed,
        ),
        tuple(labels),
        references,
    )


def _dollar_display_math(
    document: SourceDocument,
    smap: SourceMap,
    dollar_ranges: Sequence[tuple[int, int, int, int]],
) -> tuple[
    tuple[DisplayMathFact, ...],
    tuple[EquationLabelFact, ...],
    tuple[EquationRefFact, ...],
]:
    display: list[DisplayMathFact] = []
    labels: list[EquationLabelFact] = []
    references: list[EquationRefFact] = []
    for start, body_start, body_end, _close_end in dollar_ranges:
        fact_id = f"{document.path.as_posix()}::display-math::{start}"
        body_text = document.text[body_start:body_end]
        body = body_text.strip()
        if not body:
            continue
        span_start = body_start + len(body_text) - len(body_text.lstrip())
        span_end = body_start + len(body_text.rstrip())
        label_facts = list(_tex_label_facts(document, smap, fact_id, body_start, body_text))
        label_facts.extend(_dollar_tail_label_facts(document, smap, fact_id, body_end))
        reference_facts = tuple(
            _tex_reference_facts(document, smap, fact_id, body_start, body_text)
        )
        labels.extend(label_facts)
        references.extend(reference_facts)
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
    return tuple(display), tuple(labels), tuple(references)


def _tex_reference_facts(
    document: SourceDocument,
    smap: SourceMap,
    fact_id: str,
    body_start: int,
    body_text: str,
) -> Iterable[EquationRefFact]:
    lexical = scan_tex_lexically(body_text)
    active_body = lexical.active_text
    for match in _TEX_REFERENCE_RE.finditer(active_body):
        if is_escaped(body_text, match.start()) or range_contains(
            match.start(), lexical.non_math_ranges
        ):
            continue
        target = match.group("target").strip()
        if not target:
            continue
        raw_target = match.group("target")
        leading = len(raw_target) - len(raw_target.lstrip())
        target_start = body_start + match.start("target") + leading
        role_start = body_start + match.start()
        role_end = body_start + match.end()
        yield EquationRefFact(
            fact_id=f"{fact_id}::ref::{target_start}",
            document_id=document.path.as_posix(),
            span=smap.span(role_start, role_end),
            raw=match.group(0),
            ref_kind=f"tex-{match.group('kind')}",
            target=target,
            normalized_target=normalize_label(target),
            source_block_id=fact_id,
            role_span=smap.span(role_start, role_end),
            target_span=smap.span(target_start, target_start + len(target)),
        )


def _tex_label_facts(
    document: SourceDocument,
    smap: SourceMap,
    fact_id: str,
    body_start: int,
    body_text: str,
) -> Iterable[EquationLabelFact]:
    lexical = scan_tex_lexically(body_text)
    active_body = lexical.active_text
    for match in TEX_LABEL_RE.finditer(active_body):
        if is_escaped(body_text, match.start()) or range_contains(
            match.start(), lexical.non_math_ranges
        ):
            continue
        label = match.group("label")
        if not label.strip():
            continue
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
        if not label:
            continue
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
