import pytest

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Severity
from scieqlint.policy.host import PolicyHost


def diagnostic(code: str, severity: Severity = Severity.WARNING) -> DiagnosticIR:
    return DiagnosticIR(
        code=code,
        message=f"{code} message",
        span=None,
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


def test_unknown_profile_is_rejected_before_analysis():
    with pytest.raises(ValueError, match="unknown profile: typo"):
        PolicyHost().make_plan(("typo",))
