"""Architecture adapter for the stable algebra checker."""

from __future__ import annotations

from scieqlint.check.algebra import check_algebra
from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.facts.math import DisplayMathFact
from scieqlint.query.host import QueryHost
from scieqlint.scan.base import MathBlock, MathContainer


class AlgebraEngine:
    name = "algebra"
    rule_codes = frozenset(
        {"ALG001", "ALG010", "ALG020", "ALG030", "PARSE020", "PARSE021", "PARSE022"}
    )

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        for fact in query.math.display_math():
            span = fact.span
            if span is None:
                continue
            diagnostics.extend(
                _diagnostic_to_ir(diagnostic)
                for diagnostic in check_algebra(_math_block_from_fact(fact, span))
            )
        return tuple(diagnostics)


def _math_block_from_fact(fact: DisplayMathFact, span: SourceSpan) -> MathBlock:
    container = (
        MathContainer.MARKDOWN_FENCE
        if fact.container == "fenced-math"
        else MathContainer.MARKDOWN_DISPLAY
    )
    return MathBlock(
        text=fact.body,
        span=span,
        block_id=fact.fact_id,
        container=container,
    )


def _diagnostic_to_ir(diagnostic: Diagnostic) -> DiagnosticIR:
    return DiagnosticIR(
        code=diagnostic.code,
        message=diagnostic.message,
        span=diagnostic.span,
        severity_default=diagnostic.severity,
        detail=diagnostic.detail,
        hint=diagnostic.hint,
        rule=diagnostic.rule,
        false_positive_risk="low",
    )
