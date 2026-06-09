"""SARIF 2.1.0 reporter."""

from __future__ import annotations

import hashlib
import json

from scieqlint import __version__
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import CheckResult, Diagnostic, Severity, SourceSpan

JsonValue = str | int | bool | None | dict[str, "JsonValue"] | list["JsonValue"]

_LEVELS = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INFO: "note",
}
DEFAULT_MAX_RESULTS = 5000


class SarifReporter:
    def __init__(self, *, max_results: int = DEFAULT_MAX_RESULTS) -> None:
        if max_results < 0:
            raise ValueError("max_results must be non-negative")
        self.max_results = max_results

    def render(self, result: CheckResult) -> str:
        diagnostics = tuple(
            diagnostic for diagnostic in result.diagnostics if not diagnostic.suppressed
        )
        if len(diagnostics) > self.max_results:
            raise ValueError(
                f"SARIF result limit exceeded: {len(diagnostics)} > {self.max_results}"
            )
        payload: dict[str, JsonValue] = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "SciEqLint",
                            "semanticVersion": result.version or __version__,
                            "rules": _rules(diagnostics),
                        }
                    },
                    "results": [_result(diagnostic) for diagnostic in diagnostics],
                }
            ],
        }
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _rules(diagnostics: tuple[Diagnostic, ...]) -> list[JsonValue]:
    codes = sorted({diagnostic.code for diagnostic in diagnostics})
    rules: list[JsonValue] = []
    for code in codes:
        info = CATALOG.get(code)
        rules.append(
            {
                "id": code,
                "name": code,
                "shortDescription": {
                    "text": info.message if info is not None else code,
                },
                "help": {
                    "text": info.meaning if info is not None else code,
                },
            }
        )
    return rules


def _result(diagnostic: Diagnostic) -> JsonValue:
    result: dict[str, JsonValue] = {
        "ruleId": diagnostic.code,
        "level": _LEVELS[diagnostic.severity],
        "message": {"text": _message(diagnostic)},
        "partialFingerprints": {
            "primaryLocationLineHash": _fingerprint(diagnostic),
        },
    }
    if diagnostic.span is not None:
        result["locations"] = [_location(diagnostic.span)]
    return result


def _message(diagnostic: Diagnostic) -> str:
    if diagnostic.detail:
        return f"{diagnostic.message}: {diagnostic.detail}"
    return diagnostic.message


def _location(span: SourceSpan) -> JsonValue:
    location: dict[str, JsonValue] = {
        "physicalLocation": {
            "artifactLocation": {
                "uri": span.path.as_posix(),
                "uriBaseId": "%SRCROOT%",
            },
            "region": {
                "startLine": span.line,
                "startColumn": span.col,
                "endLine": span.end_line,
                "endColumn": span.end_col + 1,
            },
        }
    }
    if span.cell is not None:
        location["logicalLocations"] = [
            {
                "fullyQualifiedName": f"cell:{span.cell}",
                "kind": "module",
            }
        ]
    return location


def _fingerprint(diagnostic: Diagnostic) -> str:
    span = diagnostic.span
    path = "" if span is None else span.path.as_posix()
    line_col = "" if span is None else f"{span.line}:{span.col}:{span.end_line}:{span.end_col}"
    signal = diagnostic.equation or diagnostic.detail or diagnostic.message
    payload = "\0".join([diagnostic.code, path, line_col, signal])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
