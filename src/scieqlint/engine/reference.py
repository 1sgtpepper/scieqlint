"""Reference diagnostics over ``ReferenceQueryView``."""

from __future__ import annotations

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.ir import DiagnosticIR
from scieqlint.facts.reference import EquationLabelFact, EquationRefFact, GenericRefFact
from scieqlint.query.host import QueryHost


class ReferenceEngine:
    name = "references"
    rule_codes = frozenset({"REF001", "REF002", "REF004", "REF005", "REF011"})

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        duplicate_equation_info = CATALOG["REF001"]
        duplicate_targets = query.references.duplicate_equation_targets().values()
        duplicate_groups = tuple(
            sorted(
                (tuple(sorted(same_name, key=_fact_source_key)) for same_name in duplicate_targets),
                key=lambda facts: _fact_source_key(facts[0]),
            )
        )
        for same_name in duplicate_groups:
            for duplicate in same_name[1:]:
                diagnostics.append(
                    DiagnosticIR(
                        code=duplicate_equation_info.code,
                        severity_default=duplicate_equation_info.severity,
                        message=f"{duplicate_equation_info.message}: {duplicate.normalized_label}",
                        span=duplicate.label_span or duplicate.span,
                        rule="references",
                        false_positive_risk="low",
                    )
                )
        missing_equation_info = CATALOG["REF002"]
        for ref in sorted(
            query.references.unresolved_equation_refs(),
            key=_fact_source_key,
        ):
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
        ambiguous_equation_info = CATALOG["REF011"]
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
        equation_missing_info = CATALOG["REF002"]
        for ref in sorted(
            query.references.unresolved_generic_refs(),
            key=_fact_source_key,
        ):
            if ref.role_kind == "markdown-link":
                diagnostics.append(
                    DiagnosticIR(
                        code=equation_missing_info.code,
                        severity_default=equation_missing_info.severity,
                        message=f"{equation_missing_info.message}: {ref.target}",
                        span=ref.target_span or ref.span,
                        detail=f"reference text: {ref.raw}",
                        rule="references",
                        false_positive_risk="low",
                    )
                )
                continue
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
        for ref in sorted(
            query.references.ambiguous_generic_refs(),
            key=_fact_source_key,
        ):
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
        return tuple(sorted(diagnostics, key=_diagnostic_key))


def _fact_source_key(
    fact: EquationLabelFact | EquationRefFact | GenericRefFact,
) -> tuple[str, int, int, int, str, str]:
    span = (
        fact.label_span or fact.span
        if isinstance(fact, EquationLabelFact)
        else fact.target_span or fact.span
    )
    return (
        fact.document_id,
        -1 if span is None or span.cell is None else span.cell,
        -1 if span is None else span.start,
        -1 if span is None else span.end,
        fact.fact_id,
        fact.raw or "",
    )


def _diagnostic_key(
    diagnostic: DiagnosticIR,
) -> tuple[str, int, int, int, str, str, str, str, str]:
    span = diagnostic.span
    return (
        "" if span is None else span.path.as_posix(),
        -1 if span is None or span.cell is None else span.cell,
        -1 if span is None else span.start,
        -1 if span is None else span.end,
        diagnostic.code,
        diagnostic.message,
        diagnostic.detail or "",
        diagnostic.rule or "",
        diagnostic.hint or "",
    )
