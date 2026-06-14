"""JSON renderer for architecture-preview AnalysisResult."""

from __future__ import annotations

import json
from typing import cast

from scieqlint.diag.model import Diagnostic
from scieqlint.schema.result import AnalysisResult

JsonValue = str | int | bool | None | dict[str, "JsonValue"] | list["JsonValue"]


def render_analysis_result_json(result: AnalysisResult, *, show_suppressed: bool = False) -> str:
    diagnostics = tuple(
        diagnostic
        for diagnostic in result.diagnostics
        if not diagnostic.suppressed or show_suppressed
    )
    summary = cast(dict[str, JsonValue], _summary(result, diagnostics))
    facts_summary: dict[str, JsonValue] = {
        "headings": len(result.snapshot.headings),
        "target_anchors": len(result.snapshot.target_anchors),
        "generic_refs": len(result.snapshot.generic_refs),
        "inline_math": len(result.snapshot.inline_math),
        "display_math": len(result.snapshot.display_math),
        "unknown_math": len(result.snapshot.unknown_math),
        "code_cells": len(result.snapshot.code_cells),
    }
    payload: dict[str, JsonValue] = {
        "schema_version": result.schema_version,
        "tool": "scieqlint",
        "profiles": list(result.profiles),
        "summary": summary,
        "diagnostics": [_diagnostic_json(diagnostic) for diagnostic in diagnostics],
        "facts_summary": facts_summary,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _summary(
    result: AnalysisResult,
    diagnostics: tuple[Diagnostic, ...],
) -> dict[str, int]:
    unsuppressed = tuple(diagnostic for diagnostic in diagnostics if not diagnostic.suppressed)
    return {
        "files_checked": len(result.snapshot.documents),
        "facts": len(result.snapshot.all_facts()),
        "diagnostics": len(diagnostics),
        "errors": sum(1 for d in unsuppressed if d.severity.value == "error"),
        "warnings": sum(1 for d in unsuppressed if d.severity.value == "warning"),
        "info": sum(1 for d in unsuppressed if d.severity.value == "info"),
    }


def _diagnostic_json(diagnostic: Diagnostic) -> dict[str, JsonValue]:
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
        "detail": diagnostic.detail,
        "hint": diagnostic.hint,
        "rule": diagnostic.rule,
        "suppressed": diagnostic.suppressed,
    }
    if diagnostic.suppressed:
        diagnostic_json["suppression_reason"] = diagnostic.suppression_reason or "suppressed"
    return diagnostic_json
