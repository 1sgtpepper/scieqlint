from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.diag.model import CheckResult, Diagnostic, Severity, SourceSpan
from scieqlint.report.github import GitHubReporter


def test_github_report_is_silent_for_clean_result() -> None:
    result = CheckResult(
        diagnostics=(),
        files_checked=1,
        math_blocks_checked=0,
        config_path=None,
        version="0.1.0",
    )

    assert GitHubReporter().render(result) == ""


def test_github_report_emits_annotation_location_and_title() -> None:
    result = CheckResult(
        diagnostics=(
            Diagnostic(
                code="ALG001",
                severity=Severity.ERROR,
                message="algebraic identity does not hold",
                span=SourceSpan(
                    path=PurePosixPath("examples/bad/famous_bad.md"),
                    start=3,
                    end=12,
                    line=5,
                    col=2,
                    end_line=5,
                    end_col=11,
                ),
                detail="left - right = 2*a*b",
            ),
        ),
        files_checked=1,
        math_blocks_checked=1,
        config_path=None,
        version="0.1.0",
    )

    assert GitHubReporter().render(result) == (
        "::error title=ALG001 algebraic identity does not hold,"
        "file=examples/bad/famous_bad.md,line=5,col=2,endLine=5,endColumn=11"
        "::left - right = 2*a*b\n"
    )


def test_github_report_omits_suppressed_diagnostics() -> None:
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

    assert GitHubReporter().render(result) == ""


def test_github_report_escapes_workflow_command_data_and_properties() -> None:
    result = CheckResult(
        diagnostics=(
            Diagnostic(
                code="REF002",
                severity=Severity.WARNING,
                message="target, not: found",
                span=SourceSpan(
                    path=PurePosixPath("docs/eq:one,two.md"),
                    start=0,
                    end=1,
                    line=1,
                    col=1,
                    end_line=1,
                    end_col=2,
                ),
                detail="100% missing\r\nnext",
            ),
        ),
        files_checked=1,
        math_blocks_checked=0,
        config_path=None,
        version="0.1.0",
    )

    assert GitHubReporter().render(result) == (
        "::warning title=REF002 target%2C not%3A found,"
        "file=docs/eq%3Aone%2Ctwo.md,line=1,col=1,endLine=1,endColumn=2"
        "::100%25 missing%0D%0Anext\n"
    )


def test_github_report_maps_info_to_notice() -> None:
    result = CheckResult(
        diagnostics=(
            Diagnostic(
                code="PARSE021",
                severity=Severity.INFO,
                message="unsupported function",
                span=None,
            ),
        ),
        files_checked=1,
        math_blocks_checked=1,
        config_path=None,
        version="0.1.0",
    )

    assert (
        GitHubReporter().render(result)
        == "::notice title=PARSE021 unsupported function::unsupported function\n"
    )


def test_github_report_hides_suppressed_diagnostics() -> None:
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

    assert GitHubReporter().render(result) == ""
