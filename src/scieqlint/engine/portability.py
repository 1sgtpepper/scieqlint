"""Output-profile diagnostics over structured portability facts."""

from __future__ import annotations

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.facts.math import InlineMathFact
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.policy import PolicyHost
from scieqlint.query.host import QueryHost
from scieqlint.query.portability import NotebookRenderingConflict


class PortabilityEngine:
    name = "portability"
    rule_codes = frozenset({"PORT001", "PORT002", "PORT003", "PORT004"})

    def __init__(self, *, profile: str, policy: PolicyHost | None = None) -> None:
        self.profile = profile
        self.policy = policy or PolicyHost()

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        if self.profile == "math-accessibility":
            return tuple(
                self._inline_accessibility_diagnostic(fact)
                for fact in query.portability.inline_math_missing_alt()
            )
        if self.profile == "typst-portability":
            diagnostics: list[DiagnosticIR] = []
            for fact in query.portability.risks():
                if fact.risk_kind not in {
                    "typst-unsupported-command",
                    "typst-fragile-environment",
                }:
                    raise ValueError(f"unsupported Typst portability risk kind: {fact.risk_kind}")
                diagnostics.append(self._typst_syntax_diagnostic(fact))
            return tuple(diagnostics)
        if self.profile == "notebook-crossrefs":
            return tuple(
                self._notebook_renderings_diagnostic(conflict)
                for conflict in query.portability.notebook_rendering_conflicts()
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
                ("subject_fact_id", fact.fact_id),
            ),
        )

    def _notebook_renderings_diagnostic(
        self,
        conflict: NotebookRenderingConflict,
    ) -> DiagnosticIR:
        cell = conflict.cell
        output = conflict.output
        location = output or cell
        label = cell.label or "<caption-only cell>"
        output_detail = ""
        output_properties: tuple[tuple[str, str], ...] = ()
        if output is not None:
            output_detail = f" at output {output.output_index}"
            output_properties = (("output_index", str(output.output_index)),)
        provenance_ids = (
            (cell.fact_id, output.fact_id) if output is not None else (cell.fact_id,)
        )
        return DiagnosticIR(
            code="PORT004",
            severity_default=self.policy.severity("PORT004"),
            message="cell renderings are incompatible with cross-reference options",
            span=location.span,
            detail=(
                f"cell {label!r}{output_detail} combines renderings={conflict.renderings!r} "
                f"with {list(conflict.crossref_options)!r}"
            ),
            hint=(
                "Keep renderings on a cell without cross-reference options, or move "
                "the labeled figure/table structure outside the rendered cell."
            ),
            rule="portability.notebook_renderings_crossref",
            profile_gated=True,
            false_positive_risk="low",
            profile=self.profile,
            provenance_ids=provenance_ids,
            properties=(
                ("label", label),
                ("renderings", conflict.renderings),
                ("crossref_options", ",".join(conflict.crossref_options)),
                ("source_format", cell.source_format),
                ("subject_fact_id", cell.fact_id),
                *output_properties,
            ),
        )

    def _typst_syntax_diagnostic(
        self,
        fact: OutputPortabilityFact,
    ) -> DiagnosticIR:
        metadata = dict(fact.metadata)
        syntax_kind = metadata["syntax_kind"]
        if syntax_kind == "command":
            token = metadata["token"]
            detail = f"TeX command {token} is outside the focused Typst baseline"
            properties = (
                ("output_profile", fact.output_profile),
                ("syntax_kind", syntax_kind),
                ("token", token),
                ("command", metadata["command"]),
                ("subject_fact_id", fact.subject_fact_id),
            )
        elif syntax_kind == "environment":
            environment = metadata["environment"]
            detail = f"{environment} combined with TeX delimiter sizing is fragile in Typst export"
            properties = (
                ("output_profile", fact.output_profile),
                ("syntax_kind", syntax_kind),
                ("environment", environment),
                ("delimiter_commands", metadata["delimiter_commands"]),
                ("subject_fact_id", fact.subject_fact_id),
            )
        else:
            raise ValueError(f"unsupported Typst syntax kind: {syntax_kind}")
        return DiagnosticIR(
            code="PORT003",
            severity_default=self.policy.severity("PORT003"),
            message="equation syntax may not survive Typst export",
            span=fact.span,
            detail=detail,
            hint=(
                "Rewrite the focused TeX form before Typst export or verify the "
                "generated Typst with the publishing toolchain."
            ),
            rule="portability.typst_equation_syntax",
            profile_gated=True,
            false_positive_risk="medium",
            profile=self.profile,
            properties=properties,
        )
