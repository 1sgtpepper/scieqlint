from pathlib import PurePosixPath

import pytest

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Severity, SourceSpan
from scieqlint.policy.host import PolicyHost


def diagnostic(
    code: str,
    severity: Severity = Severity.WARNING,
    span: SourceSpan | None = None,
) -> DiagnosticIR:
    return DiagnosticIR(
        code=code,
        message=f"{code} message",
        span=span,
        severity_default=severity,
    )


def test_scientific_myst_strict_ci_remaps_selected_rule_to_error():
    host = PolicyHost()
    plan = host.make_plan(("scientific-myst", "strict-ci"))

    diagnostics = host.apply((diagnostic("STR001"),), plan)

    assert diagnostics[0].code == "STR001"
    assert diagnostics[0].severity is Severity.ERROR


def test_default_profile_filters_unselected_rule():
    host = PolicyHost()
    plan = host.make_plan(("default",))

    diagnostics = host.apply((diagnostic("STR001"), diagnostic("STR002")), plan)

    assert [diagnostic.code for diagnostic in diagnostics] == ["STR002"]


def test_generated_profile_is_standalone_document_gate():
    plan = PolicyHost().make_plan(("generated",))

    assert plan.engines == frozenset({"structure", "references", "math-container", "generated"})
    assert {
        "STR001",
        "REF001",
        "REF002",
        "REF010",
        "REF011",
        "REF014",
        "GEN003",
        "MATH020",
    } <= plan.rules
    assert dict(plan.severity_overrides)["REF011"] is Severity.ERROR


def test_strict_ci_alone_inherits_default_analysis_scope():
    plan = PolicyHost().make_plan(("strict-ci",))

    assert "structure" in plan.engines
    assert "STR002" in plan.rules
    assert dict(plan.severity_overrides)["STR001"] is Severity.ERROR


def test_policy_application_sorts_diagnostics_by_source_location():
    host = PolicyHost()
    plan = host.make_plan(())

    diagnostics = host.apply(
        (
            diagnostic("STR002", span=_span("b.md", 2, 1)),
            diagnostic("STR002", span=_span("a.md", 3, 1)),
        ),
        plan,
    )

    assert [item.span.path.as_posix() for item in diagnostics if item.span is not None] == [
        "a.md",
        "b.md",
    ]


def test_unknown_profile_is_rejected_before_analysis():
    with pytest.raises(ValueError, match="unknown profile: typo"):
        PolicyHost().make_plan(("typo",))


def _span(path: str, line: int, col: int) -> SourceSpan:
    return SourceSpan(
        path=PurePosixPath(path),
        start=0,
        end=1,
        line=line,
        col=col,
        end_line=line,
        end_col=col + 1,
    )
