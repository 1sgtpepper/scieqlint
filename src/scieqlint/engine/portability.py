"""Output-profile diagnostics over structured portability facts."""

from __future__ import annotations

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.policy import PolicyHost
from scieqlint.query.host import QueryHost


class PortabilityEngine:
    name = "portability"
    rule_codes = frozenset({"PORT001"})

    def __init__(self, *, profile: str, policy: PolicyHost) -> None:
        self.profile = profile
        self.policy = policy

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        return tuple(
            self._equation_reference_diagnostic(fact)
            for fact in query.portability.risks("equation-reference-syntax")
        )

    def _equation_reference_diagnostic(
        self,
        fact: OutputPortabilityFact,
    ) -> DiagnosticIR:
        metadata = dict(fact.metadata)
        ref_kind = metadata["ref_kind"]
        target = metadata["target"]
        return DiagnosticIR(
            code="PORT001",
            severity_default=self.policy.severity("PORT001"),
            message="equation reference syntax may not survive configured output profile",
            span=fact.span,
            detail=(
                f"{ref_kind} reference to '{target}' is not in the "
                f"{fact.output_profile} portability baseline"
            ),
            hint="Use reference syntax supported by the configured publishing target.",
            rule="portability.equation_reference_syntax",
            profile_gated=True,
            false_positive_risk="medium",
            profile=self.profile,
            properties=(
                ("output_profile", fact.output_profile),
                ("ref_kind", ref_kind),
                ("target", target),
                ("subject_fact_id", fact.subject_fact_id),
            ),
        )
