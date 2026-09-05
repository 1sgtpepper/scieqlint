"""Output-profile diagnostics over structured portability facts."""

from __future__ import annotations

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.facts.math import InlineMathFact
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.policy import PolicyHost
from scieqlint.query.host import QueryHost


class PortabilityEngine:
    name = "portability"
    rule_codes = frozenset({"PORT001", "PORT002"})

    def __init__(self, *, profile: str, policy: PolicyHost) -> None:
        self.profile = profile
        self.policy = policy

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        if self.profile == "math-accessibility":
            return tuple(
                self._inline_accessibility_diagnostic(fact)
                for fact in query.portability.inline_math_missing_alt()
            )
        if self.profile != "cross-format-references":
            raise ValueError(f"unsupported portability profile: {self.profile}")

        diagnostics: list[DiagnosticIR] = []
        for fact in query.portability.risks():
            if fact.risk_kind != "equation-reference-syntax":
                raise ValueError(f"unsupported portability risk kind: {fact.risk_kind}")
            diagnostics.append(self._equation_reference_diagnostic(fact))
        return tuple(diagnostics)

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

    def _inline_accessibility_diagnostic(
        self,
        fact: InlineMathFact,
    ) -> DiagnosticIR:
        delimiter_kind = fact.delimiter_kind
        text_role = fact.surrounding_text_role
        parse_status = fact.parse_status
        return DiagnosticIR(
            code="PORT002",
            severity_default=self.policy.severity("PORT002"),
            message="inline math lacks accessible text metadata",
            span=fact.span,
            detail=(
                f"{delimiter_kind} inline math in {text_role} content has no "
                "configured accessible text"
            ),
            hint=(
                "Provide accessible text through the publishing workflow, or use "
                "a display equation form that supports it."
            ),
            rule="portability.inline_math_accessible_text",
            profile_gated=True,
            false_positive_risk="medium",
            profile=self.profile,
            properties=(
                ("accessibility_requirement", "accessible-text"),
                ("delimiter_kind", delimiter_kind),
                ("surrounding_text_role", text_role),
                ("parse_status", parse_status),
                *(
                    (("accessibility_id", fact.accessibility_id),)
                    if fact.accessibility_id is not None
                    else ()
                ),
                ("subject_fact_id", fact.fact_id),
            ),
        )
