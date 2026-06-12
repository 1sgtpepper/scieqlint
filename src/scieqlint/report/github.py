"""GitHub workflow command reporter."""

from __future__ import annotations

from scieqlint.diag.model import CheckResult, Diagnostic, Severity
from scieqlint.report.base import cell_location_prefix

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
        properties.append(("file", span.path.as_posix()))
        if span.cell is None:
            properties.extend(
                [
                    ("line", str(span.line)),
                    ("col", str(span.col)),
                    ("endLine", str(span.end_line)),
                    ("endColumn", str(span.end_col)),
                ]
            )
    properties_text = ",".join(f"{name}={_escape_property(value)}" for name, value in properties)
    message = _message(diagnostic)
    return f"::{command} {properties_text}::{_escape_data(message)}"


def _message(diagnostic: Diagnostic) -> str:
    message = diagnostic.detail if diagnostic.detail else diagnostic.message
    if diagnostic.span is None:
        return message
    prefix = cell_location_prefix(diagnostic.span)
    if prefix is None:
        return message
    return f"{prefix}: {message}"


def _escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")
