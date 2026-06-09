"""Text reporter."""

from __future__ import annotations

from scieqlint.diag.model import CheckResult


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
            if diagnostic.detail:
                lines.append(f"  detail: {diagnostic.detail}")
        return "\n".join(lines) + "\n"
