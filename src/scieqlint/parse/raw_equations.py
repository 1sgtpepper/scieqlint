"""Equation labels and references from accepted raw display math."""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import replace

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.math import DisplayMathFact
from scieqlint.facts.reference import EquationLabelFact, EquationRefFact
from scieqlint.markdown import is_escaped, range_contains, scan_tex_lexically
from scieqlint.source.maps import SourceMap

from .normalize import splitline_starts

_TEX_LABEL_RE = re.compile(r"\\label\{(?P<label>[^{}\r\n]+)\}")
_TEX_REFERENCE_RE = re.compile(r"\\(?P<kind>eqref|ref)\{(?P<target>[^{}\r\n]+)\}")


def raw_equation_facts(
    fact: DisplayMathFact,
    source_map: SourceMap,
) -> tuple[tuple[EquationLabelFact, ...], tuple[EquationRefFact, ...]]:
    """Materialize facts from a complete raw candidate outside opaque containers."""

    assert fact.span is not None, "raw-LaTeX candidates must retain source spans"
    raw = fact.raw or ""
    lexical = scan_tex_lexically(raw)
    active_raw = lexical.active_text
    opaque_ranges = lexical.non_math_ranges
    line_starts = splitline_starts(raw) if fact.span.cell_line is not None else ()
    labels: list[EquationLabelFact] = []
    references: list[EquationRefFact] = []
    for match in _TEX_LABEL_RE.finditer(active_raw):
        if is_escaped(raw, match.start()) or range_contains(match.start(), opaque_ranges):
            continue
        label = match.group("label")
        if not label.strip():
            continue
        label_start = match.start("label")
        label_span = _raw_subspan(
            fact,
            source_map,
            label_start,
            label_start + len(label),
            line_starts,
        )
        labels.append(
            EquationLabelFact(
                fact_id=(
                    f"{fact.fact_id}::label::"
                    f"{label_start if fact.span.segments else label_span.start}"
                ),
                document_id=fact.document_id,
                span=label_span,
                raw=label,
                label=label,
                normalized_label=_normalize_label(label),
                label_syntax_kind="tex-label",
                source_block_id=fact.fact_id,
                label_span=label_span,
            )
        )
    for match in _TEX_REFERENCE_RE.finditer(active_raw):
        if is_escaped(raw, match.start()) or range_contains(match.start(), opaque_ranges):
            continue
        raw_target = match.group("target")
        target = raw_target.strip()
        if not target:
            continue
        leading = len(raw_target) - len(raw_target.lstrip())
        target_start = match.start("target") + leading
        role_start = match.start()
        role_end = match.end()
        role_span = _raw_subspan(fact, source_map, role_start, role_end, line_starts)
        target_span = _raw_subspan(
            fact,
            source_map,
            target_start,
            target_start + len(target),
            line_starts,
        )
        references.append(
            EquationRefFact(
                fact_id=(
                    f"{fact.fact_id}::ref::"
                    f"{target_start if fact.span.segments else target_span.start}"
                ),
                document_id=fact.document_id,
                span=role_span,
                raw=match.group(0),
                ref_kind=f"tex-{match.group('kind')}",
                target=target,
                normalized_target=_normalize_label(target),
                source_block_id=fact.fact_id,
                role_span=role_span,
                target_span=target_span,
            )
        )
    return tuple(labels), tuple(references)


def _raw_subspan(
    fact: DisplayMathFact,
    source_map: SourceMap,
    start: int,
    end: int,
    line_starts: tuple[int, ...],
) -> SourceSpan:
    """Map a raw-equation subspan without reconstructing notebook source text."""

    assert fact.span is not None, "raw-LaTeX candidates must retain source spans"
    raw = fact.raw or ""
    # Regex match offsets are bounded by ``raw`` before they reach this mapper.
    if start < 0 or end <= start or end > len(raw):  # pragma: no cover
        raise ValueError("raw equation subspan is outside its source text")
    cell_line = (
        None
        if fact.span.cell_line is None
        else fact.span.cell_line + bisect_right(line_starts, start) - 1
    )
    if fact.span.segments:
        if len(fact.span.segments) != len(raw):
            raise ValueError("raw equation source mapping does not match its source text")
        segments = fact.span.segments[start:end]
        first = segments[0]
        last = segments[-1]
        return replace(
            fact.span,
            start=first.start,
            end=last.end,
            line=first.line,
            col=first.col,
            end_line=last.end_line,
            end_col=last.end_col,
            cell_line=cell_line,
            segments=segments,
        )
    mapped = source_map.span(fact.span.start + start, fact.span.start + end)
    return replace(
        mapped,
        cell=fact.span.cell,
        cell_line=cell_line,
    )


def _normalize_label(value: str) -> str:
    value = value.strip()
    return value[1:] if value.startswith("#") else value
