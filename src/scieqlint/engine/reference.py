"""Reference diagnostics over ``ReferenceQueryView``."""

from __future__ import annotations

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Severity
from scieqlint.query.host import QueryHost


class ReferenceEngine:
    name = "references"
    rule_codes = frozenset({"REF010", "REF011", "REF012", "REF013"})

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        diagnostics.extend(self._duplicate_targets(query))
        diagnostics.extend(self._unresolved_refs(query))
        diagnostics.extend(self._ambiguous_refs(query))
        diagnostics.extend(self._orphaned_targets(query))
        return tuple(diagnostics)

    def _duplicate_targets(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        out: list[DiagnosticIR] = []
        for label, anchors in query.references.duplicate_generic_targets().items():
            for duplicate in anchors[1:]:
                out.append(
                    DiagnosticIR(
                        code="REF010",
                        severity_default=Severity.ERROR,
                        message=f"duplicate MyST target anchor: {label}",
                        span=duplicate.label_span or duplicate.span,
                        detail=f"First definition and duplicate both normalize to {label!r}.",
                        rule="reference.duplicate_generic_anchor",
                        false_positive_risk="low",
                    )
                )
        return tuple(out)

    def _unresolved_refs(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        out: list[DiagnosticIR] = []
        for ref in query.references.unresolved_generic_refs():
            out.append(
                DiagnosticIR(
                    code="REF011",
                    severity_default=Severity.WARNING,
                    message=f"generic reference target not found: {ref.target}",
                    span=ref.target_span or ref.span,
                    detail=ref.raw,
                    hint="Restore the `(label)=` anchor or correct the reference target.",
                    rule="reference.missing_generic_target",
                    false_positive_risk="low",
                )
            )
        return tuple(out)

    def _ambiguous_refs(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        out: list[DiagnosticIR] = []
        for ref in query.references.ambiguous_generic_refs():
            out.append(
                DiagnosticIR(
                    code="REF012",
                    severity_default=Severity.WARNING,
                    message=f"generic reference target is ambiguous: {ref.target}",
                    span=ref.target_span or ref.span,
                    detail=ref.raw,
                    rule="reference.ambiguous_generic_target",
                    false_positive_risk="medium",
                )
            )
        return tuple(out)

    def _orphaned_targets(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        out: list[DiagnosticIR] = []
        for anchor in query.references.orphaned_targets():
            out.append(
                DiagnosticIR(
                    code="REF013",
                    severity_default=Severity.WARNING,
                    message="MyST target anchor is not attached to a following block: "
                    f"{anchor.label}",
                    span=anchor.label_span or anchor.span,
                    hint="Move the anchor immediately before the heading or block it labels.",
                    rule="reference.orphaned_anchor",
                    profile_gated=True,
                    false_positive_risk="medium",
                )
            )
        return tuple(out)
