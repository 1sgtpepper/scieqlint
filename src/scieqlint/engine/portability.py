"""Portability/profile diagnostics."""

from __future__ import annotations

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Severity
from scieqlint.query.host import QueryHost


class PortabilityEngine:
    name = "portability"
    rule_codes = frozenset({"PORT001", "PORT002", "PORT003", "PORT004"})

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        diagnostics.extend(self._math_alt_diagnostics(query))
        diagnostics.extend(self._quarto_crossref_diagnostics(query))
        return tuple(diagnostics)

    def _math_alt_diagnostics(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        out: list[DiagnosticIR] = []
        for fact in query.portability.inline_math_missing_alt():
            out.append(
                DiagnosticIR(
                    code="PORT001",
                    severity_default=Severity.INFO,
                    message="inline math has no portable alt text",
                    span=fact.span,
                    detail=fact.body,
                    rule="portability.inline_math_alt",
                    profile_gated=True,
                    false_positive_risk="high",
                )
            )
        for fact in query.portability.display_math_missing_alt():
            out.append(
                DiagnosticIR(
                    code="PORT002",
                    severity_default=Severity.WARNING,
                    message="display math has no portable alt text",
                    span=fact.span,
                    detail=fact.body[:120],
                    rule="portability.display_math_alt",
                    profile_gated=True,
                    false_positive_risk="medium",
                )
            )
        return tuple(out)

    def _quarto_crossref_diagnostics(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        out: list[DiagnosticIR] = []
        for cell in query.portability.quarto_crossref_label_issues():
            out.append(
                DiagnosticIR(
                    code="PORT003",
                    severity_default=Severity.WARNING,
                    message="Quarto cross-reference label has no recognized type prefix: "
                    f"{cell.label}",
                    span=cell.span,
                    hint="Use a prefix such as fig-, tbl-, eq-, or lst- for "
                    "cross-referenceable labels.",
                    rule="quarto.crossref_prefix",
                    profile_gated=True,
                    false_positive_risk="low",
                )
            )
        for cell in query.portability.renderings_with_crossref_options():
            out.append(
                DiagnosticIR(
                    code="PORT004",
                    severity_default=Severity.WARNING,
                    message="Quarto cell combines renderings with crossref-producing options",
                    span=cell.span,
                    detail=str(cell.options),
                    hint="Use renderings on the cell and express figures/subfigures "
                    "with fenced divs.",
                    rule="quarto.renderings_crossref",
                    profile_gated=True,
                    false_positive_risk="low",
                )
            )
        return tuple(out)
