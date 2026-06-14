"""Structure diagnostics over ``StructureQueryView``."""

from __future__ import annotations

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Severity
from scieqlint.query.host import QueryHost


class StructureEngine:
    name = "structure"
    rule_codes = frozenset({"STR001", "STR002", "STR003", "STR004", "DIR010"})

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        diagnostics.extend(self._heading_diagnostics(query))
        diagnostics.extend(self._fence_diagnostics(query))
        diagnostics.extend(self._code_cell_diagnostics(query))
        return tuple(diagnostics)

    def _heading_diagnostics(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        out: list[DiagnosticIR] = []
        for heading in query.structure.malformed_headings():
            out.append(
                DiagnosticIR(
                    code="STR001",
                    severity_default=Severity.WARNING,
                    message="ATX heading marker must be followed by a space",
                    span=heading.marker_span or heading.span,
                    detail=heading.raw,
                    hint="Use '# Title' rather than '#Title'.",
                    rule="structure.heading_spacing",
                    profile_gated=True,
                    false_positive_risk="low",
                )
            )
        return tuple(out)

    def _fence_diagnostics(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        out: list[DiagnosticIR] = []
        for fence in query.structure.unclosed_fences():
            out.append(
                DiagnosticIR(
                    code="STR002",
                    severity_default=Severity.WARNING,
                    message="fenced block is missing its closing delimiter",
                    span=fence.opener_span,
                    detail=fence.info_string or fence.opener,
                    hint="Close the block with a matching fence line.",
                    rule="structure.fence_closed",
                    false_positive_risk="low",
                )
            )
        for fence in query.structure.fences():
            if fence.kind == "generic" and not fence.info_string.strip():
                out.append(
                    DiagnosticIR(
                        code="STR003",
                        severity_default=Severity.INFO,
                        message="fenced code block has no language/info string",
                        span=fence.opener_span,
                        hint="Add a language, or disable this rule for intentionally "
                        "generic fences.",
                        rule="structure.fence_language",
                        profile_gated=True,
                        false_positive_risk="medium",
                    )
                )
        return tuple(out)

    def _code_cell_diagnostics(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        out: list[DiagnosticIR] = []
        for cell in query.structure.code_cells():
            if cell.language:
                continue
            out.append(
                DiagnosticIR(
                    code="DIR010",
                    severity_default=Severity.WARNING,
                    message="code-cell directive is missing an executable language",
                    span=cell.span,
                    hint="Use a directive argument such as ```{code-cell} python.",
                    rule="directive.code_cell_language",
                    profile_gated=True,
                    false_positive_risk="medium",
                )
            )
        return tuple(out)
