"""Semantic classification of generated-formula candidates."""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import replace

from scieqlint.facts.generated import GeneratedFormulaFact, GeneratedFormulaKind
from scieqlint.facts.math import InlineMathFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.markdown import is_escaped, without_tex_comments
from scieqlint.source.maps import SourceMap

from .normalize import splitline_starts

_MAX_SPACED_TOKEN_PARTS = 64
_SPACED_COMMAND_RE = re.compile(
    rf"(?P<artifact>"
    rf"\\[ \t]*(?:[A-Za-z][ \t]+){{3,{_MAX_SPACED_TOKEN_PARTS}}}[A-Za-z](?=[ \t]*[\[{{])"
    rf"|(?<![A-Za-z0-9_\\])[A-Z](?:[ \t]+[A-Za-z]){{3,{_MAX_SPACED_TOKEN_PARTS}}}"
    rf"(?=[ \t]*\([ \t]*[A-Za-z][ \t]*(?:,[ \t]*[A-Za-z][ \t]*){{2,{_MAX_SPACED_TOKEN_PARTS}}}\))"
    rf")"
)
_GARBLED_MARKER_RE = re.compile(r"(?<![A-Za-z0-9_])(?P<artifact>/C0[ \t]+apod)(?![A-Za-z0-9_])")


def classify_generated_formulas(snapshot: FactSnapshot) -> tuple[GeneratedFormulaFact, ...]:
    source_maps = {
        document.path.as_posix(): SourceMap.for_document(document)
        for document in snapshot.documents
    }
    inline_math = {fact.fact_id: fact for fact in snapshot.inline_math}
    facts: list[GeneratedFormulaFact] = []
    for candidate in snapshot.generated_formulas:
        if candidate.kind != "candidate":
            facts.append(candidate)
            continue
        source_map = source_maps.get(candidate.document_id)
        assert source_map is not None
        assert candidate.span is not None
        facts.extend(_classify_generated_candidate(candidate, source_map, inline_math))
    return tuple(
        sorted(
            facts,
            key=lambda fact: (fact.span.start if fact.span is not None else -1, fact.fact_id),
        )
    )


def _classify_generated_candidate(
    candidate: GeneratedFormulaFact,
    source_map: SourceMap,
    inline_math: dict[str, InlineMathFact],
) -> tuple[GeneratedFormulaFact, ...]:
    if candidate.candidate_kind == "formula-text":
        return _suspicious_formula_facts(candidate, source_map)
    if candidate.candidate_kind == "bracketed-block":
        assert candidate.delimiter_kind is not None
        return (
            replace(
                candidate,
                kind="bracketed-block",
                candidate_kind=None,
                delimiter_kind=candidate.delimiter_kind,
            ),
        )
    if candidate.candidate_kind == "placeholder":
        if candidate.placeholder_kind == "empty-display-math":
            kind: GeneratedFormulaKind = "empty-display"
        elif candidate.placeholder_kind == "formula-image":
            kind = "image-placeholder"
        else:
            kind = "placeholder"
        return (replace(candidate, kind=kind, candidate_kind=None),)
    assert candidate.candidate_kind == "equation-like-text"
    assert candidate.source_math_fact_id is not None
    source_math = inline_math.get(candidate.source_math_fact_id)
    if source_math is None or source_math.parse_status != "text-leak":
        return ()
    return (
        replace(
            candidate,
            kind="equation-like-text",
            candidate_kind=None,
            confidence="inferred",
        ),
    )


def _suspicious_formula_facts(
    candidate: GeneratedFormulaFact,
    source_map: SourceMap,
) -> tuple[GeneratedFormulaFact, ...]:
    assert candidate.span is not None
    patterns: tuple[tuple[GeneratedFormulaKind, re.Pattern[str]], ...] = (
        ("spaced-token", _SPACED_COMMAND_RE),
        ("garbled-marker", _GARBLED_MARKER_RE),
    )
    facts: list[GeneratedFormulaFact] = []
    active_text = without_tex_comments(candidate.text)
    line_starts = splitline_starts(candidate.text) if candidate.span.cell_line is not None else ()
    for kind, pattern in patterns:
        for match in pattern.finditer(active_text):
            local_start, local_end = match.span("artifact")
            artifact = candidate.text[local_start:local_end]
            if kind == "spaced-token":
                if artifact.startswith("\\") and is_escaped(candidate.text, local_start):
                    continue
                if not artifact.startswith("\\") and not _starts_spaced_token_run(
                    active_text, local_start
                ):
                    continue
                if not _high_confidence_spaced_command(artifact):
                    continue
            start = candidate.span.start + local_start
            end = candidate.span.start + local_end
            artifact_span = source_map.span(start, end)
            fact_id = f"{candidate.document_id}::generated-formula::{kind}::{start}"
            if candidate.span.segments:
                if len(candidate.span.segments) != len(candidate.text):
                    raise ValueError(
                        "generated formula source mapping does not match its source text"
                    )
                segments = candidate.span.segments[local_start:local_end]
                first = segments[0]
                last = segments[-1]
                artifact_span = replace(
                    candidate.span,
                    start=first.start,
                    end=last.end,
                    line=first.line,
                    col=first.col,
                    end_line=last.end_line,
                    end_col=last.end_col,
                    cell_line=(
                        None
                        if candidate.span.cell_line is None
                        else candidate.span.cell_line + bisect_right(line_starts, local_start) - 1
                    ),
                    segments=segments,
                )
                fact_id = f"{candidate.fact_id}::{kind}::{local_start}"
            facts.append(
                GeneratedFormulaFact(
                    fact_id=fact_id,
                    document_id=candidate.document_id,
                    span=artifact_span,
                    raw=artifact,
                    confidence="inferred",
                    kind=kind,
                    text=artifact,
                    candidate_kind=None,
                    source_math_fact_id=candidate.source_math_fact_id,
                )
            )
    return tuple(facts)



def _starts_spaced_token_run(text: str, start: int) -> bool:
    # A bounded regex match must not restart inside a longer continuous run.
    end = start
    while end > 0 and text[end - 1] in " \t":
        end -= 1
    if end == start:
        return True
    previous = text[max(0, end - 2) : end]
    return re.fullmatch(r"(?:[^A-Za-z0-9_])?[A-Za-z]", previous) is None



def _high_confidence_spaced_command(artifact: str) -> bool:
    letters = re.findall(r"[A-Za-z]", artifact)
    return len(letters) >= 4 and sum(letter.islower() for letter in letters) >= 2
