from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

from scieqlint.diag.model import CheckResult, Diagnostic, Severity, SourceSpan
from scieqlint.report.sarif import SarifReporter


def test_sarif_report_has_stable_top_level_shape_and_rule_metadata() -> None:
    payload = json.loads(SarifReporter().render(_result()))

    assert payload["$schema"] == "https://json.schemastore.org/sarif-2.1.0.json"
    assert payload["version"] == "2.1.0"
    run = payload["runs"][0]
    assert run["tool"]["driver"]["name"] == "SciEqLint"
    assert run["tool"]["driver"]["semanticVersion"] == "0.1.0"
    assert run["tool"]["driver"]["rules"][0]["id"] == "ALG001"


def test_sarif_report_emits_locations_and_partial_fingerprints() -> None:
    payload = json.loads(SarifReporter().render(_result()))

    sarif_result = payload["runs"][0]["results"][0]
    assert sarif_result["ruleId"] == "ALG001"
    assert sarif_result["level"] == "error"
    assert sarif_result["message"]["text"] == (
        "algebraic identity does not hold: left - right = 2*a*b"
    )
    assert sarif_result["locations"][0]["physicalLocation"] == {
        "artifactLocation": {
            "uri": "examples/bad/famous_bad.md",
            "uriBaseId": "%SRCROOT%",
        },
        "region": {
            "startLine": 4,
            "startColumn": 1,
            "endLine": 4,
            "endColumn": 20,
        },
    }
    fingerprint = sarif_result["partialFingerprints"]["primaryLocationLineHash"]
    assert len(fingerprint) == 64
    assert (
        fingerprint
        == json.loads(SarifReporter().render(_result()))["runs"][0]["results"][0][
            "partialFingerprints"
        ]["primaryLocationLineHash"]
    )


def test_sarif_report_preserves_notebook_cell_location_metadata() -> None:
    result = CheckResult(
        diagnostics=(
            Diagnostic(
                code="INP002",
                severity=Severity.WARNING,
                message="notebook schema issue",
                span=SourceSpan(
                    path=PurePosixPath("notes.ipynb"),
                    start=0,
                    end=0,
                    line=1,
                    col=1,
                    end_line=1,
                    end_col=1,
                    cell=3,
                    cell_line=1,
                ),
                detail="markdown cell 3 source must be a string or string list",
            ),
        ),
        files_checked=1,
        math_blocks_checked=0,
        config_path=None,
        version="0.1.0",
    )

    payload = json.loads(SarifReporter().render(result))

    assert payload["runs"][0]["results"][0]["locations"][0]["logicalLocations"] == [
        {
            "fullyQualifiedName": "cell:3",
            "kind": "module",
        }
    ]


def test_sarif_report_omits_suppressed_diagnostics() -> None:
    result = CheckResult(
        diagnostics=(
            Diagnostic(
                code="ALG001",
                severity=Severity.ERROR,
                message="algebraic identity does not hold",
                span=None,
                suppressed=True,
            ),
        ),
        files_checked=1,
        math_blocks_checked=1,
        config_path=None,
        version="0.1.0",
    )

    payload = json.loads(SarifReporter().render(result))

    assert payload["runs"][0]["tool"]["driver"]["rules"] == []
    assert payload["runs"][0]["results"] == []


def test_sarif_result_limit_guard_fails_deterministically() -> None:
    result = CheckResult(
        diagnostics=(_diagnostic("ALG001"), _diagnostic("REF002")),
        files_checked=1,
        math_blocks_checked=1,
        config_path=None,
        version="0.1.0",
    )

    with pytest.raises(ValueError, match="SARIF result limit exceeded: 2 > 1"):
        SarifReporter(max_results=1).render(result)


def test_sarif_result_limit_rejects_negative_values() -> None:
    with pytest.raises(ValueError, match="max_results must be non-negative"):
        SarifReporter(max_results=-1)


def test_sarif_report_hides_suppressed_diagnostics() -> None:
    result = CheckResult(
        diagnostics=(
            Diagnostic(
                code="ALG001",
                severity=Severity.ERROR,
                message="algebraic identity does not hold",
                span=SourceSpan(
                    path=PurePosixPath("paper.md"),
                    start=0,
                    end=1,
                    line=1,
                    col=1,
                    end_line=1,
                    end_col=1,
                ),
                suppressed=True,
            ),
        ),
        files_checked=1,
        math_blocks_checked=1,
        config_path=None,
        version="0.1.0",
    )

    payload = json.loads(SarifReporter().render(result))

    assert payload["runs"][0]["results"] == []
    assert payload["runs"][0]["tool"]["driver"]["rules"] == []


def _result() -> CheckResult:
    return CheckResult(
        diagnostics=(
            Diagnostic(
                code="ALG001",
                severity=Severity.ERROR,
                message="algebraic identity does not hold",
                span=SourceSpan(
                    path=PurePosixPath("examples/bad/famous_bad.md"),
                    start=3,
                    end=21,
                    line=4,
                    col=1,
                    end_line=4,
                    end_col=19,
                ),
                equation="(a+b)^2 = a^2 + b^2",
                detail="left - right = 2*a*b",
            ),
        ),
        files_checked=1,
        math_blocks_checked=1,
        config_path=None,
        version="0.1.0",
    )


def _diagnostic(code: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        severity=Severity.WARNING,
        message=f"{code} message",
        span=SourceSpan(
            path=PurePosixPath("paper.md"),
            start=0,
            end=1,
            line=1,
            col=1,
            end_line=1,
            end_col=1,
        ),
    )
