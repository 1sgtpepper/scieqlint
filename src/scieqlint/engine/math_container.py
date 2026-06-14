"""Math-container and UnknownMath diagnostics."""

from __future__ import annotations

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Severity
from scieqlint.query.host import QueryHost


class MathContainerEngine:
    name = "math-container"
    rule_codes = frozenset({"MATH020", "MATH021"})

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        for unknown in query.math.unknown_math():
            diagnostics.append(
                DiagnosticIR(
                    code="MATH020",
                    severity_default=Severity.INFO,
                    message=f"unsupported or unknown math: {unknown.reason}",
                    span=unknown.span,
                    detail=unknown.excerpt,
                    hint="Keep unsupported math valid for the renderer, or configure the "
                    "profile to ignore this class.",
                    rule="math.unknown",
                    false_positive_risk="low",
                )
            )
        for fact in query.math.display_with_multiple_labels():
            diagnostics.append(
                DiagnosticIR(
                    code="MATH021",
                    severity_default=Severity.WARNING,
                    message="display math contains multiple labels",
                    span=fact.span,
                    detail=", ".join(fact.label_fact_ids),
                    hint="Use a renderer-supported multi-equation reference pattern, "
                    "or split equations.",
                    rule="math.multiple_labels",
                    profile_gated=True,
                    false_positive_risk="medium",
                )
            )
        return tuple(diagnostics)
