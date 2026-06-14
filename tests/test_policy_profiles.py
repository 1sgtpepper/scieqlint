from pathlib import PurePosixPath

import pytest

from scieqlint.compat.architecture_pipeline import analyze_documents_architecture
from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Severity
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.policy.host import PolicyHost


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath("lecture.md"), text, DocumentKind.MARKDOWN)


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


def test_unknown_profile_is_rejected_before_analysis():
    with pytest.raises(ValueError, match="unknown profile: typo"):
        PolicyHost().make_plan(("typo",))


def test_architecture_pipeline_applies_strict_ci_severity():
    result = analyze_documents_architecture(
        (doc("####Title\n"),),
        profiles=("scientific-myst", "strict-ci"),
    )

    diag = next(d for d in result.diagnostics if d.code == "STR001")
    assert diag.severity.value == "error"


def test_architecture_pipeline_default_profile_filters_heading_style():
    result = analyze_documents_architecture((doc("####Title\n"),), profiles=("default",))

    assert "STR001" not in [d.code for d in result.diagnostics]
