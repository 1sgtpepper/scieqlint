from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.diag.model import CheckResult, Diagnostic, Severity, SourceSpan
from scieqlint.report.text import TextReporter


def test_empty_text_report_names_checked_counts() -> None:
    result = CheckResult(
        diagnostics=(),
        files_checked=2,
        math_blocks_checked=3,
        config_path=None,
        version="0.1.0",
    )
    rendered = TextReporter().render(result)
    assert "found no diagnostics" in rendered
    assert "files checked: 2" in rendered
    assert "math blocks checked: 3" in rendered


def test_text_report_marks_suppressed_diagnostics() -> None:
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

    assert "paper.md:1:1: suppressed error ALG001" in TextReporter().render(result)
