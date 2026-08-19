"""Reference diagnostics over ``ReferenceQueryView``."""

from __future__ import annotations

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.ir import DiagnosticIR
from scieqlint.facts.reference import EquationLabelFact, EquationRefFact
from scieqlint.query.host import QueryHost


class ReferenceEngine:
    name = "references"
    rule_codes = frozenset({"REF001", "REF002", "REF004", "REF005", "REF009"})

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        duplicate_equation_info = CATALOG["REF001"]
        duplicate_targets = query.references.duplicate_equation_targets().values()
        for same_name in sorted(duplicate_targets, key=lambda facts: _fact_source_key(facts[0])):
            for duplicate in sorted(same_name, key=_fact_source_key)[1:]:
                diagnostics.append(
                    DiagnosticIR(
                        code=duplicate_equation_info.code,
                        severity_default=duplicate_equation_info.severity,
                        message=(f"{duplicate_equation_info.message}: {duplicate.label}"),
                        span=duplicate.label_span or duplicate.span,
                        rule="references",
                        false_positive_risk="low",
                    )
                )
        missing_equation_info = CATALOG["REF002"]
        for ref in query.references.unresolved_equation_refs():
            diagnostics.append(
                DiagnosticIR(
                    code=missing_equation_info.code,
                    severity_default=missing_equation_info.severity,
                    message=f"{missing_equation_info.message}: {ref.target}",
                    span=ref.target_span or ref.span,
                    detail=f"reference text: {ref.raw}",
                    rule="references",
                    false_positive_risk="low",
                )
            )
        ambiguous_equation_info = CATALOG["REF009"]
        for ref in sorted(
            query.references.ambiguous_equation_refs(),
            key=_fact_source_key,
        ):
            diagnostics.append(
                DiagnosticIR(
                    code=ambiguous_equation_info.code,
                    severity_default=ambiguous_equation_info.severity,
                    message=f"{ambiguous_equation_info.message}: {ref.target}",
                    span=ref.target_span or ref.span,
                    detail=f"reference text: {ref.raw}",
                    rule="references.equation_target_ambiguous",
                    false_positive_risk="low",
                )
            )
        missing_info = CATALOG["REF004"]
        for ref in query.references.unresolved_generic_refs():
            if ref.role_kind != "ref":
                continue
            diagnostics.append(
                DiagnosticIR(
                    code=missing_info.code,
                    severity_default=missing_info.severity,
                    message=f"{missing_info.message}: {ref.target}",
                    span=ref.target_span or ref.span,
                    detail=f"reference text: {ref.raw}",
                    rule="references.generic_target",
                    false_positive_risk="low",
                )
            )
        ambiguous_info = CATALOG["REF005"]
        for ref in query.references.ambiguous_generic_refs():
            if ref.role_kind != "ref":
                continue
            diagnostics.append(
                DiagnosticIR(
                    code=ambiguous_info.code,
                    severity_default=ambiguous_info.severity,
                    message=f"{ambiguous_info.message}: {ref.target}",
                    span=ref.target_span or ref.span,
                    detail=f"reference text: {ref.raw}",
                    rule="references.generic_target_ambiguous",
                    false_positive_risk="low",
                )
            )
        return tuple(diagnostics)


def _fact_source_key(
    fact: EquationLabelFact | EquationRefFact,
) -> tuple[str, int, int, str]:
    span = (
        fact.label_span
        if isinstance(fact, EquationLabelFact)
        else fact.target_span or fact.span
    )
    return (
        fact.document_id,
        -1 if span is None else span.start,
        -1 if span is None else span.end,
        fact.fact_id,
    )
