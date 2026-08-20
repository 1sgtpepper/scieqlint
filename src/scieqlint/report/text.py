"""Text reporter."""

from __future__ import annotations

from scieqlint.diag.model import CheckResult
from scieqlint.schema import SchemaHost


class TextReporter:
    def __init__(self, *, quiet: bool = False) -> None:
        self.quiet = quiet

    def render(self, result: CheckResult) -> str:
        diagnostics = tuple(
            diagnostic
            for diagnostic in result.diagnostics
            if not diagnostic.suppressed or result.show_suppressed
        )
        if not diagnostics:
            if self.quiet:
                return ""
            return (
                "SciEqLint found no diagnostics\n"
                f"files checked: {result.files_checked}\n"
                f"math blocks checked: {result.math_blocks_checked}\n"
            )
        lines: list[str] = []
        for diagnostic in diagnostics:
            span = diagnostic.span
            location = "<unknown>" if span is None else f"{span.path}:{span.line}:{span.col}"
            status = " suppressed" if diagnostic.suppressed else ""
            lines.append(
                f"{location}:{status} {diagnostic.severity.value} "
                f"{diagnostic.code} {diagnostic.message}"
            )
            projection = SchemaHost.project_diagnostic(diagnostic)
            if diagnostic.equation:
                lines.append(f"  equation: {diagnostic.equation}")
            if diagnostic.detail:
                lines.append(f"  detail: {diagnostic.detail}")
            if projection.profile is not None:
                lines.append(f"  profile: {projection.profile}")
            if projection.provenance_ids:
                lines.append(f"  provenance: {', '.join(projection.provenance_ids)}")
            for name, value in projection.properties:
                lines.append(f"  {name}: {value}")
        return "\n".join(lines) + "\n"
