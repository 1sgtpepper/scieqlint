from __future__ import annotations

import pytest

from scieqlint.diag.model import Diagnostic, DiagnosticProvenance, Severity
from scieqlint.facts.generated import GeneratedProvenanceFact
from scieqlint.schema import DIAGNOSTIC_PROJECTION_VERSION, SchemaHost


def test_schema_host_preserves_the_legacy_empty_projection_shape() -> None:
    diagnostic = Diagnostic("REF002", Severity.WARNING, "missing target", None)

    projection = SchemaHost.project_diagnostic(diagnostic)

    assert projection.version == DIAGNOSTIC_PROJECTION_VERSION
    assert projection.profile is None
    assert projection.provenance_ids == ()
    assert projection.properties == ()


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
    assert SchemaHost.generated_provenance_properties(provenance, prefix="origin_") == (
        ("origin_generated_document", "out/generated.md"),
        ("origin_source_document", "source/paper.tex"),
        ("origin_source_kind", "latex"),
        ("origin_conversion_stage", "translation"),
    )


def test_schema_host_projects_semantic_diagnostic_provenance() -> None:
    diagnostic = Diagnostic(
        "GEN004",
        Severity.WARNING,
        "formula placeholder",
        None,
        provenance=(
            DiagnosticProvenance(
                fact_id="out/generated.md::generated-provenance",
                generated_document_id="out/generated.md",
                source_kind="latex",
            ),
        ),
    )

    projection = SchemaHost.project_diagnostic(diagnostic)

    assert projection.provenance_ids == ("out/generated.md::generated-provenance",)
    assert projection.properties == (
        ("generated_document", "out/generated.md"),
        ("source_kind", "latex"),
    )
