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


def test_text_report_hides_suppressed_diagnostics_by_default() -> None:
    result = _suppressed_result(show_suppressed=False)

    rendered = TextReporter().render(result)

    assert "found no diagnostics" in rendered
    assert "ALG001" not in rendered


def test_text_report_marks_suppressed_diagnostics_when_enabled() -> None:
    result = _suppressed_result(show_suppressed=True)

    assert "paper.md:1:1: suppressed error ALG001" in TextReporter().render(result)


def test_text_report_includes_equation_before_detail() -> None:
    result = CheckResult(
        diagnostics=(
            Diagnostic(
                code="ALG001",
                severity=Severity.ERROR,
                message="algebraic identity does not hold",
                span=None,
                equation="left = right",
                detail="left - right = 1",
            ),
        ),
        files_checked=1,
        math_blocks_checked=1,
        config_path=None,
        version="0.1.0",
    )

    assert TextReporter().render(result).splitlines() == [
        "<unknown>: error ALG001 algebraic identity does not hold",
        "  equation: left = right",
        "  detail: left - right = 1",
    ]


def test_text_report_includes_profile_provenance_and_properties() -> None:
    result = CheckResult(
        diagnostics=(
            Diagnostic(
                code="GEN001",
                severity=Severity.WARNING,
                message="generated output is missing a preserved anchor",
                span=None,
                profile="generated-myst",
                provenance_ids=("out/paper.md::generated-provenance",),
                properties=(("generated_document", "out/paper.md"),),
            ),
        ),
        files_checked=1,
        math_blocks_checked=0,
        config_path=None,
        version="0.1.0",
    )

    assert TextReporter().render(result).splitlines() == [
        "<unknown>: warning GEN001 generated output is missing a preserved anchor",
        "  profile: generated-myst",
        "  provenance: out/paper.md::generated-provenance",
        "  generated_document: out/paper.md",
    ]


def _suppressed_result(*, show_suppressed: bool) -> CheckResult:
    return CheckResult(
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
        show_suppressed=show_suppressed,
    )
