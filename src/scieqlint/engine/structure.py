"""Structure diagnostics over ``StructureQueryView``."""

from __future__ import annotations

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Severity
from scieqlint.facts.structure import HeadingFact
from scieqlint.query.host import QueryHost


class StructureEngine:
    name = "structure"
    rule_codes = frozenset(
        {
            "STR001",
            "STR002",
            "STR003",
            "STR004",
            "STR005",
            "DIR001",
            "DIR002",
            "DIR010",
            "DIR011",
            "DIR012",
        }
    )

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        diagnostics.extend(self._heading_diagnostics(query))
        diagnostics.extend(self._heading_hierarchy_diagnostics(query))
        diagnostics.extend(self._fence_diagnostics(query))
        diagnostics.extend(self._code_cell_diagnostics(query))
        diagnostics.extend(self._syntax_diagnostics(query))
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

    def _heading_hierarchy_diagnostics(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        out: list[DiagnosticIR] = []
        headings_by_document: dict[str, list[HeadingFact]] = {}
        for heading in query.structure.headings():
            headings_by_document.setdefault(heading.document_id, []).append(heading)

        for headings in headings_by_document.values():
            previous_level = 0
            top_level_count = 0
            for heading in headings:
                if heading.level == 1:
                    top_level_count += 1
                    if top_level_count > 1:
                        out.append(
                            DiagnosticIR(
                                code="STR005",
                                severity_default=Severity.WARNING,
                                message="document has more than one top-level heading",
                                span=heading.marker_span or heading.span,
                                detail=heading.raw,
                                hint="Use one level-1 heading and nest later sections below it.",
                                rule="structure.single_top_level_heading",
                                profile_gated=True,
                                false_positive_risk="medium",
                            )
                        )
                if previous_level and heading.level > previous_level + 1:
                    out.append(
                        DiagnosticIR(
                            code="STR004",
                            severity_default=Severity.WARNING,
                            message="heading level skips an intermediate parent",
                            span=heading.marker_span or heading.span,
                            detail=heading.raw,
                            hint=(
                                f"Use a level-{previous_level + 1} heading before this "
                                f"level-{heading.level} heading."
                            ),
                            rule="structure.heading_hierarchy",
                            profile_gated=True,
                            false_positive_risk="medium",
                        )
                    )
                previous_level = heading.level
        return tuple(out)

    def _fence_diagnostics(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        out: list[DiagnosticIR] = []
        for fence in query.structure.unclosed_fences():
            if fence.kind == "math":
                continue
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

    def _syntax_diagnostics(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        out: list[DiagnosticIR] = []
        for issue in query.structure.syntax_issues():
            if issue.kind == "myst-directive":
                out.append(
                    DiagnosticIR(
                        code="DIR001",
                        severity_default=Severity.WARNING,
                        message="MyST directive fence info string is malformed",
                        span=issue.span,
                        detail=issue.raw,
                        hint="Use a directive opener such as ```{note} or ```{code-cell} python.",
                        rule="directive.syntax",
                        profile_gated=True,
                        false_positive_risk="low",
                    )
                )
            elif issue.kind == "myst-option":
                out.append(
                    DiagnosticIR(
                        code="DIR002",
                        severity_default=Severity.WARNING,
                        message="MyST directive option line is malformed",
                        span=issue.span,
                        detail=issue.raw,
                        hint="Use ':name: value' option syntax before directive content.",
                        rule="directive.option_syntax",
                        profile_gated=True,
                        false_positive_risk="low",
                    )
                )
            elif issue.kind == "myst-role":
                out.append(
                    DiagnosticIR(
                        code="DIR011",
                        severity_default=Severity.WARNING,
                        message="MyST role syntax is malformed",
                        span=issue.span,
                        detail=issue.raw,
                        hint="Use role syntax such as {ref}`target` or {ref}`Title <target>`.",
                        rule="directive.role_syntax",
                        profile_gated=True,
                        false_positive_risk="low",
                    )
                )
            elif issue.kind == "code-cell-tags":
                out.append(
                    DiagnosticIR(
                        code="DIR012",
                        severity_default=Severity.WARNING,
                        message="code-cell tags option is malformed",
                        span=issue.span,
                        detail=issue.raw,
                        hint="Use comma-separated tags or a bracketed list such as [hide-input].",
                        rule="directive.code_cell_tags",
                        profile_gated=True,
                        false_positive_risk="low",
                    )
                )
        return tuple(out)
