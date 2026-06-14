"""Generated-document validation diagnostics."""

from __future__ import annotations

from scieqlint.diag.ir import DiagnosticIR, RelatedLocation
from scieqlint.diag.model import Severity
from scieqlint.query.host import QueryHost


class GeneratedOutputEngine:
    name = "generated"
    rule_codes = frozenset({"GEN002", "GEN003", "REF014"})

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        diagnostics.extend(self._dropped_target_diagnostics(query))
        diagnostics.extend(self._generated_unresolved_ref_diagnostics(query))
        return tuple(diagnostics)

    def _dropped_target_diagnostics(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        out: list[DiagnosticIR] = []
        for prov, source_anchor in query.generated.dropped_targets():
            related = (
                (RelatedLocation(source_anchor.span, "source anchor"),)
                if source_anchor.span is not None
                else ()
            )
            out.append(
                DiagnosticIR(
                    code="REF014",
                    severity_default=Severity.ERROR,
                    message="generated document dropped required MyST anchor: "
                    f"{source_anchor.label}",
                    span=source_anchor.label_span or source_anchor.span,
                    detail=f"source={prov.source_document_id}; "
                    f"generated={prov.generated_document_id}",
                    hint="Generated outputs must preserve `(label)=` anchors verbatim.",
                    rule="generated.preserved_anchor_inventory",
                    profile_gated=True,
                    false_positive_risk="low",
                    related_locations=related,
                )
            )
        return tuple(out)

    def _generated_unresolved_ref_diagnostics(
        self,
        query: QueryHost,
    ) -> tuple[DiagnosticIR, ...]:
        generated_ids = set(query.generated.generated_document_ids())
        generated_target_labels = {
            anchor.normalized_label
            for anchor in query.references.generic_targets()
            if anchor.document_id in generated_ids
        }
        out: list[DiagnosticIR] = []
        for ref in query.references.generic_refs():
            if ref.document_id not in generated_ids:
                continue
            if ref.normalized_target in generated_target_labels:
                continue
            out.append(
                DiagnosticIR(
                    code="GEN003",
                    severity_default=Severity.ERROR,
                    message="generated document introduced or preserved unresolved reference: "
                    f"{ref.target}",
                    span=ref.target_span or ref.span,
                    detail=ref.raw,
                    rule="generated.no_new_unresolved_refs",
                    profile_gated=True,
                    false_positive_risk="low",
                )
            )
        return tuple(out)
