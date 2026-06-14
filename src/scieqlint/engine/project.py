"""Project graph diagnostics."""

from __future__ import annotations

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Severity
from scieqlint.query.host import QueryHost


class ProjectGraphEngine:
    name = "project"
    rule_codes = frozenset({"PROJ002"})

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        for normalized, members in query.project.duplicate_normalized_paths().items():
            for member in members[1:]:
                diagnostics.append(
                    DiagnosticIR(
                        code="PROJ002",
                        severity_default=Severity.WARNING,
                        message="project file appears under multiple normalized paths: "
                        f"{normalized}",
                        span=member.span,
                        detail=member.path.as_posix(),
                        hint="Normalize project chapter paths, avoiding unnecessary './' prefixes.",
                        rule="project.normalized_paths",
                        profile_gated=True,
                        false_positive_risk="medium",
                    )
                )
        return tuple(diagnostics)
