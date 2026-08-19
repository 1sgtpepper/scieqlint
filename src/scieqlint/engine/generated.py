"""Generated-output diagnostics over ``GeneratedOutputQueryView``."""

from __future__ import annotations

from collections.abc import Iterable

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Severity
from scieqlint.facts.generated import GeneratedFormulaFact
from scieqlint.query.host import QueryHost
from scieqlint.schema import SchemaHost


class GeneratedOutputEngine:
    def __init__(self, *, profile: str | None = None) -> None:
        self.profile = profile

    name = "generated-output"
    rule_codes = frozenset({"GEN001", "GEN002", "GEN003"})

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
                    properties=SchemaHost.generated_provenance_properties(provenance),
                )
            )
        diagnostics.extend(
            self._suspicious_formula_diagnostic(query, fact)
            for fact in query.generated.suspicious_formula_text()
        )
        diagnostics.extend(
            self._bracketed_latex_diagnostic(query, fact)
            for fact in query.generated.bracketed_latex_blocks()
        )
        return tuple(diagnostics)

    def _suspicious_formula_diagnostic(
        self,
        query: QueryHost,
        fact: GeneratedFormulaFact,
    ) -> DiagnosticIR:
        provenance_ids, properties = _fact_metadata(
            query,
            fact,
            (("formula_artifact_kind", fact.kind),),
        )
        return DiagnosticIR(
            code="GEN002",
            severity_default=Severity.WARNING,
            message="generated math contains suspicious formula text",
            span=fact.span,
            detail=f"{fact.kind} artifact: {fact.text!r}",
            hint="Restore the intended LaTeX formula before publishing or conversion.",
            rule="generated.suspicious_formula_text",
            profile_gated=True,
            false_positive_risk="low",
            profile=self.profile,
            provenance_ids=provenance_ids,
            properties=properties,
        )

    def _bracketed_latex_diagnostic(
        self,
        query: QueryHost,
        fact: GeneratedFormulaFact,
    ) -> DiagnosticIR:
        complete = fact.complete is True
        provenance_ids, properties = _fact_metadata(
            query,
            fact,
            (
                ("formula_artifact_kind", fact.kind),
                ("complete", "true" if complete else "false"),
            ),
        )
        detail = (
            r"standalone \[...\] display delimiters are not portable generated Markdown"
            if complete
            else r"standalone \[ display opener is not closed before end of file"
        )
        return DiagnosticIR(
            code="GEN003",
            severity_default=Severity.WARNING,
            message="nonstandard bracketed LaTeX display block",
            span=fact.span,
            detail=detail,
            hint="Use a supported $$ block or a MyST math directive.",
            rule="generated.bracketed_latex_block",
            profile_gated=True,
            false_positive_risk="low",
            profile=self.profile,
            provenance_ids=provenance_ids,
            properties=properties,
        )


def _fact_metadata(
    query: QueryHost,
    fact: GeneratedFormulaFact,
    properties: Iterable[tuple[str, str]],
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    provenance = tuple(
        sorted(
            query.generated.provenance_for_document(fact.document_id),
            key=lambda item: item.fact_id,
        )
    )
    projected = list(properties)
    if len(provenance) == 1:
        projected.extend(SchemaHost.generated_provenance_properties(provenance[0]))
    else:
        for index, item in enumerate(provenance, start=1):
            projected.extend(
                SchemaHost.generated_provenance_properties(
                    item,
                    prefix=f"provenance_{index}_",
                )
            )
    return tuple(item.fact_id for item in provenance), tuple(projected)
