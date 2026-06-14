"""JSON renderer for architecture-preview AnalysisResult."""

from __future__ import annotations

import json

from scieqlint.diag.model import Diagnostic
from scieqlint.schema.result import AnalysisResult

JsonValue = str | int | bool | None | dict[str, "JsonValue"] | list["JsonValue"]


def render_analysis_result_json(result: AnalysisResult) -> str:
    payload: dict[str, JsonValue] = {
        "schema_version": result.schema_version,
        "tool": "scieqlint",
        "profiles": list(result.profiles),
        "summary": result.summary(),
        "diagnostics": [_diagnostic_json(diagnostic) for diagnostic in result.diagnostics],
        "facts_summary": {
            "headings": len(result.snapshot.headings),
            "target_anchors": len(result.snapshot.target_anchors),
            "generic_refs": len(result.snapshot.generic_refs),
            "inline_math": len(result.snapshot.inline_math),
            "display_math": len(result.snapshot.display_math),
            "unknown_math": len(result.snapshot.unknown_math),
            "code_cells": len(result.snapshot.code_cells),
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _diagnostic_json(diagnostic: Diagnostic) -> dict[str, JsonValue]:
    span = diagnostic.span
    return {
        "code": diagnostic.code,
        "severity": diagnostic.severity.value,
        "message": diagnostic.message,
        "path": None if span is None else span.path.as_posix(),
        "line": None if span is None else span.line,
        "col": None if span is None else span.col,
        "end_line": None if span is None else span.end_line,
        "end_col": None if span is None else span.end_col,
        "detail": diagnostic.detail,
        "hint": diagnostic.hint,
        "rule": diagnostic.rule,
    }
