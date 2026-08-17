"""Generated-output diagnostics over ``GeneratedOutputQueryView``."""

from __future__ import annotations

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Severity
from scieqlint.facts.generated import GeneratedProvenanceFact
from scieqlint.query.host import QueryHost


class GeneratedOutputEngine:
    def __init__(self, *, profile: str | None = None) -> None:
        self.profile = profile

    name = "generated-output"
    rule_codes = frozenset({"GEN001"})

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        for provenance, source_anchor in query.generated.dropped_targets():
            diagnostics.append(
                DiagnosticIR(
                    code="GEN001",
                    severity_default=Severity.WARNING,
                    message="generated output is missing preserved source anchor",
                    span=source_anchor.label_span or source_anchor.span,
                    detail=(
                        f"source anchor '{source_anchor.label}' from "
                        f"{provenance.source_document_id} is absent in "
                        f"{provenance.generated_document_id}"
                    ),
                    hint="Keep the MyST target anchor in the generated output before building.",
                    rule="generated.preserved_anchor",
                    false_positive_risk="low",
                    profile=self.profile,
                    provenance_ids=(provenance.fact_id,),
                    properties=_provenance_properties(provenance),
                )
            )
        return tuple(diagnostics)


def _provenance_properties(
    provenance: GeneratedProvenanceFact,
) -> tuple[tuple[str, str], ...]:
    properties = [("generated_document", provenance.generated_document_id)]
    if provenance.source_document_id is not None:
        properties.append(("source_document", provenance.source_document_id))
    if provenance.source_kind is not None:
        properties.append(("source_kind", provenance.source_kind))
    if provenance.conversion_stage is not None:
        properties.append(("conversion_stage", provenance.conversion_stage))
    return tuple(properties)
