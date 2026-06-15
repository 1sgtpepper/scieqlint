"""Reference diagnostics over ``ReferenceQueryView``."""

from __future__ import annotations

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.ir import DiagnosticIR
from scieqlint.query.host import QueryHost


class ReferenceEngine:
    name = "references"
    rule_codes = frozenset({"REF004", "REF005"})

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
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
