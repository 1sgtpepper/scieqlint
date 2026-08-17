"""GitHub workflow command reporter."""

from __future__ import annotations

from scieqlint.diag.model import CheckResult, Diagnostic, Severity

_COMMANDS = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INFO: "notice",
}


class GitHubReporter:
    def render(self, result: CheckResult) -> str:
        lines = [
            _render_diagnostic(diagnostic)
            for diagnostic in result.diagnostics
            if not diagnostic.suppressed
        ]
        if not lines:
            return ""
        return "\n".join(lines) + "\n"


def _render_diagnostic(diagnostic: Diagnostic) -> str:
    command = _COMMANDS[diagnostic.severity]
    properties = [("title", f"{diagnostic.code} {diagnostic.message}")]
    if diagnostic.span is not None:
        span = diagnostic.span
        properties.extend(
            [
                ("file", span.path.as_posix()),
                ("line", str(span.line)),
                ("col", str(span.col)),
                ("endLine", str(span.end_line)),
                ("endColumn", str(span.end_col)),
            ]
        )
    properties_text = ",".join(f"{name}={_escape_property(value)}" for name, value in properties)
    message = diagnostic.detail if diagnostic.detail else diagnostic.message
    metadata = _metadata_line(diagnostic)
    if metadata:
        message = f"{message}\n{metadata}"
    return f"::{command} {properties_text}::{_escape_data(message)}"


def _escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")


def _metadata_line(diagnostic: Diagnostic) -> str:
    fields = list(diagnostic.properties)
    if diagnostic.profile is not None:
        fields.append(("profile", diagnostic.profile))
    if diagnostic.provenance_ids:
        fields.append(("provenance", ",".join(diagnostic.provenance_ids)))
    return "; ".join(f"{name}={value}" for name, value in fields)
