"""Generated-formula source facts for conservative Markdown input."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from scieqlint.facts.generated import GeneratedFormulaFact, GeneratedFormulaKind
from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.io.source import SourceDocument
from scieqlint.source.maps import SourceMap

# A normal formula may contain whitespace between identifiers. The high-confidence
# generated failure is a long identifier split into single letters and then used
# as a call, or a similarly split LaTeX command. Requiring the call/braced argument
# avoids flagging ordinary implicit multiplication such as ``a b c``.
_SPACED_CALL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<artifact>(?:[A-Za-z][ \t]+){4,}[A-Za-z]"
    r"[ \t]*\((?:[^()\r\n]|\\.){0,160}\))"
)
_SPACED_COMMAND_RE = re.compile(
    r"(?P<artifact>\\[ \t]*(?:[A-Za-z][ \t]+){3,}[A-Za-z](?=[ \t]*[\[{]))"
)
_GARBLED_MARKER_RE = re.compile(r"(?<![A-Za-z0-9_])(?P<artifact>/C0[ \t]+apod)(?![A-Za-z0-9_])")


def scan_suspicious_formula_facts(
    document: SourceDocument,
    smap: SourceMap,
    inline_math: Sequence[InlineMathFact],
    display_math: Sequence[DisplayMathFact],
) -> tuple[GeneratedFormulaFact, ...]:
    """Record high-confidence suspicious text only inside explicit math containers."""

    source_math: tuple[InlineMathFact | DisplayMathFact, ...] = (
        *display_math,
        *(fact for fact in inline_math if fact.delimiter_kind != "plain-text"),
    )
    facts: list[GeneratedFormulaFact] = []
    for math_fact in source_math:
        if math_fact.document_id != document.path.as_posix() or math_fact.span is None:
            continue
        segment = document.text[math_fact.span.start : math_fact.span.end]
        occupied: list[tuple[int, int]] = []
        patterns: tuple[tuple[GeneratedFormulaKind, re.Pattern[str]], ...] = (
            ("spaced-token", _SPACED_CALL_RE),
            ("spaced-token", _SPACED_COMMAND_RE),
            ("garbled-marker", _GARBLED_MARKER_RE),
        )
        for kind, pattern in patterns:
            facts.extend(
                _pattern_facts(
                    document,
                    smap,
                    math_fact,
                    segment,
                    kind,
                    pattern,
                    occupied,
                )
            )
    return tuple(
        sorted(
            facts,
            key=lambda fact: (fact.span.start if fact.span is not None else -1, fact.fact_id),
        )
    )


def _pattern_facts(
    document: SourceDocument,
    smap: SourceMap,
    math_fact: InlineMathFact | DisplayMathFact,
    segment: str,
    kind: GeneratedFormulaKind,
    pattern: re.Pattern[str],
    occupied: list[tuple[int, int]],
) -> Iterable[GeneratedFormulaFact]:
    assert math_fact.span is not None
    for match in pattern.finditer(segment):
        local_start, local_end = match.span("artifact")
        start = math_fact.span.start + local_start
        end = math_fact.span.start + local_end
        if any(
            start < occupied_end and occupied_start < end
            for occupied_start, occupied_end in occupied
        ):
            continue
        occupied.append((start, end))
        artifact = match.group("artifact")
        yield GeneratedFormulaFact(
            fact_id=f"{document.path.as_posix()}::generated-formula::{kind}::{start}",
            document_id=document.path.as_posix(),
            span=smap.span(start, end),
            raw=artifact,
            confidence="inferred",
            kind=kind,
            text=artifact,
            source_math_fact_id=math_fact.fact_id,
        )
