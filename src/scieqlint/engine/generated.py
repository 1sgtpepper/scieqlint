"""Generated-output diagnostics over ``GeneratedOutputQueryView``."""

from __future__ import annotations

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Severity
from scieqlint.query.host import QueryHost


class GeneratedOutputEngine:
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
                )
            )
        return tuple(diagnostics)
