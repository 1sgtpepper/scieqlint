from __future__ import annotations

import pytest

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Diagnostic, Severity
from scieqlint.facts.generated import GeneratedProvenanceFact
from scieqlint.schema import DIAGNOSTIC_PROJECTION_VERSION, SchemaHost


def test_schema_host_preserves_the_legacy_empty_projection_shape() -> None:
    diagnostic = Diagnostic("REF002", Severity.WARNING, "missing target", None)

    projection = SchemaHost.project_diagnostic(diagnostic)

    assert projection.version == DIAGNOSTIC_PROJECTION_VERSION
    assert projection.profile is None
    assert projection.provenance_ids == ()
    assert projection.properties == ()


def test_schema_host_deduplicates_input_provenance_ids() -> None:
    diagnostic = Diagnostic(
        "REF002",
        Severity.WARNING,
        "missing target",
        None,
        provenance_ids=("origin", "origin"),
    )

    projection = SchemaHost.project_diagnostic(diagnostic)

    assert projection.provenance_ids == ("origin",)


def test_schema_host_rejects_unregistered_projection_versions() -> None:
    diagnostic = Diagnostic("REF002", Severity.WARNING, "missing target", None)

    with pytest.raises(ValueError, match="unsupported diagnostic projection version"):
        SchemaHost.project_diagnostic(diagnostic, version="diagnostic-metadata/9.9")


def test_schema_host_owns_generated_provenance_property_names() -> None:
    provenance = GeneratedProvenanceFact(
        fact_id="out/generated.md::generated-provenance",
        document_id="out/generated.md",
        span=None,
        raw=None,
        confidence="generated",
        generated_document_id="out/generated.md",
        source_document_id="source/paper.tex",
        source_kind="latex",
        conversion_stage="translation",
    )

    assert SchemaHost.generated_provenance_properties(provenance) == (
        ("generated_document", "out/generated.md"),
        ("source_document", "source/paper.tex"),
        ("source_kind", "latex"),
        ("conversion_stage", "translation"),
    )


def test_diagnostic_ir_preserves_profile_and_rule_properties() -> None:
    diagnostic = DiagnosticIR(
        code="GEN001",
        message="generated output is missing a preserved anchor",
        span=None,
        severity_default=Severity.WARNING,
        profile="generated-myst",
        properties=(("rule_property", "kept"),),
    ).to_diagnostic()

    assert diagnostic.profile == "generated-myst"
    assert diagnostic.properties == (("rule_property", "kept"),)


def test_schema_host_appends_origin_properties_without_dropping_rule_metadata() -> None:
    provenance = GeneratedProvenanceFact(
        fact_id="origin-a",
        document_id="out/generated.md",
        span=None,
        confidence="generated",
        generated_document_id="out/generated.md",
        source_document_id="source/paper.md",
    )
    diagnostic = Diagnostic(
        "GEN001",
        Severity.WARNING,
        "missing anchor",
        None,
        profile="generated-myst",
        provenance_ids=("ordinary-fact",),
        properties=(("rule_property", "kept"),),
    )

    projection = SchemaHost.project_diagnostic(
        diagnostic,
        profile="generated-myst",
        provenances=(provenance,),
    )

    assert projection.provenance_ids == ("ordinary-fact", "origin-a")
    assert projection.properties == (
        ("rule_property", "kept"),
        ("generated_document", "out/generated.md"),
        ("source_document", "source/paper.md"),
    )


def test_schema_host_normalizes_rule_properties_before_schema_precedence() -> None:
    provenance = GeneratedProvenanceFact(
        fact_id="origin-a",
        document_id="out/generated.md",
        span=None,
        confidence="generated",
        generated_document_id="out/generated.md",
    )
    diagnostic = Diagnostic(
        "GEN001",
        Severity.WARNING,
        "missing anchor",
        None,
        properties=(
            ("rule_property", "first"),
            ("rule_property", "last"),
            ("profile", "rule-profile"),
            ("provenanceIds", "rule-origin"),
            ("generated_document", "rule-document.md"),
        ),
    )

    projection = SchemaHost.project_diagnostic(
        diagnostic,
        profile="generated-myst",
        provenances=(provenance, provenance),
    )

    assert projection.profile == "generated-myst"
    assert projection.provenance_ids == (provenance.fact_id,)
    assert projection.properties == (
        ("rule_property", "last"),
        ("generated_document", "out/generated.md"),
    )


def test_schema_host_names_multiple_origins_deterministically() -> None:
    first = GeneratedProvenanceFact(
        fact_id="first-origin",
        document_id="out/first.md",
        span=None,
        confidence="generated",
        generated_document_id="out/first.md",
        source_document_id="source/first.md",
    )
    second = GeneratedProvenanceFact(
        fact_id="second-origin",
        document_id="out/second.md",
        span=None,
        confidence="generated",
        generated_document_id="out/second.md",
        source_document_id="source/second.md",
    )
    diagnostic = Diagnostic(
        "GEN001",
        Severity.WARNING,
        "missing anchor",
        None,
        properties=(("rule_property", "kept"),),
    )

    projection = SchemaHost.project_diagnostic(
        diagnostic,
        provenances=(first, second),
    )

    assert projection.provenance_ids == ("first-origin", "second-origin")
    assert projection.properties == (
        ("rule_property", "kept"),
        ("provenance_1_generated_document", "out/first.md"),
        ("provenance_1_source_document", "source/first.md"),
        ("provenance_2_generated_document", "out/second.md"),
        ("provenance_2_source_document", "source/second.md"),
    )
