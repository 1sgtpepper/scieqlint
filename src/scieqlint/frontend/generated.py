"""Generated-formula source facts for conservative Markdown input."""

from __future__ import annotations

from collections.abc import Sequence

from scieqlint.facts.generated import GeneratedFormulaFact
from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.io.source import SourceDocument

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
                source_math_fact_id=math_fact.fact_id,
            )
        )
    return tuple(
        sorted(
            facts,
            key=lambda fact: (fact.span.start if fact.span is not None else -1, fact.fact_id),
        )
    )
