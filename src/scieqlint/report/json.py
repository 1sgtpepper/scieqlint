"""JSON reporter."""

from __future__ import annotations

import json

from scieqlint.diag.model import CheckResult, Severity

JsonValue = str | int | bool | None | dict[str, "JsonValue"] | list["JsonValue"]


class JsonReporter:
    def render(self, result: CheckResult) -> str:
        counts = {Severity.ERROR: 0, Severity.WARNING: 0, Severity.INFO: 0}
        diagnostics_json: list[JsonValue] = []
        for diagnostic in result.diagnostics:
            if diagnostic.suppressed and not result.show_suppressed:
                continue
            if not diagnostic.suppressed:
                counts[diagnostic.severity] += 1
            span = diagnostic.span
            diagnostic_json: dict[str, JsonValue] = {
                "code": diagnostic.code,
                "severity": diagnostic.severity.value,
                "message": diagnostic.message,
                "path": None if span is None else span.path.as_posix(),
                "line": None if span is None else span.line,
                "col": None if span is None else span.col,
                "end_line": None if span is None else span.end_line,
                "end_col": None if span is None else span.end_col,
                "cell": None if span is None else span.cell,
                "cell_line": None if span is None else span.cell_line,
                "equation": diagnostic.equation,
                "detail": diagnostic.detail,
                "hint": diagnostic.hint,
                "suppressed": diagnostic.suppressed,
            }
            if diagnostic.suppressed:
                diagnostic_json["suppression_reason"] = (
                    diagnostic.suppression_reason or "suppressed"
                )
            diagnostics_json.append(diagnostic_json)
        payload: dict[str, JsonValue] = {
            "schema_version": "0.1",
            "tool": "scieqlint",
            "version": result.version,
            "summary": {
                "files_checked": result.files_checked,
                "math_blocks_checked": result.math_blocks_checked,
                "errors": counts[Severity.ERROR],
                "warnings": counts[Severity.WARNING],
                "info": counts[Severity.INFO],
            },
            "diagnostics": diagnostics_json,
        }
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
