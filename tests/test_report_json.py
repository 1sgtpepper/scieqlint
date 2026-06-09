from __future__ import annotations

import json
from pathlib import PurePosixPath

from scieqlint.diag.model import CheckResult, Diagnostic, Severity, SourceSpan
from scieqlint.report.json import JsonReporter


def test_json_report_has_stable_summary_shape() -> None:
    result = CheckResult(
        diagnostics=(),
        files_checked=1,
        math_blocks_checked=2,
        config_path=None,
        version="0.1.0",
    )
    payload = json.loads(JsonReporter().render(result))
    assert payload["schema_version"] == "0.1"
    assert payload["summary"] == {
        "errors": 0,
        "files_checked": 1,
        "info": 0,
        "math_blocks_checked": 2,
        "warnings": 0,
    }


def test_json_report_hides_suppressed_diagnostics_by_default() -> None:
    result = CheckResult(
        diagnostics=(_suppressed_diagnostic(),),
        files_checked=1,
        math_blocks_checked=1,
        config_path=None,
        version="0.1.0",
    )

    payload = json.loads(JsonReporter().render(result))

    assert payload["diagnostics"] == []
    assert payload["summary"]["errors"] == 0


def test_json_report_includes_suppressed_diagnostics_when_enabled() -> None:
    result = CheckResult(
        diagnostics=(_suppressed_diagnostic(),),
        files_checked=1,
        math_blocks_checked=1,
        config_path=None,
        version="0.1.0",
        show_suppressed=True,
    )

    payload = json.loads(JsonReporter().render(result))

    assert payload["diagnostics"][0]["suppressed"] is True
    assert payload["diagnostics"][0]["suppression_reason"] == "source comment"
    assert payload["summary"]["errors"] == 0


def _suppressed_diagnostic() -> Diagnostic:
    return Diagnostic(
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
        suppression_reason="source comment",
    )


def test_json_report_keeps_baseline_suppression_reason_when_enabled() -> None:
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
                detail="left - right = 2*a*b",
                suppressed=True,
                suppression_reason="baseline",
            ),
        ),
        files_checked=1,
        math_blocks_checked=1,
        config_path=None,
        version="0.1.0",
        show_suppressed=True,
    )

    payload = json.loads(JsonReporter().render(result))

    assert payload["summary"]["errors"] == 0
    assert payload["diagnostics"][0]["suppressed"] is True
    assert payload["diagnostics"][0]["suppression_reason"] == "baseline"
