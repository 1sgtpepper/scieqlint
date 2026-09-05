from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

from scieqlint.api import check_documents
from scieqlint.app import _generated_provenance_facts, _project_generated_diagnostic
from scieqlint.config.model import Config, ProfileConfig, ScannerConfig
from scieqlint.diag.model import CheckResult, Diagnostic, Severity, SourceSpan
from scieqlint.facts.generated import GeneratedProvenanceFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.query.host import QueryHost
from scieqlint.report.github import GitHubReporter
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter
from scieqlint.report.text import TextReporter
from scieqlint.schema import DIAGNOSTIC_PROJECTION_VERSION, SchemaHost


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def test_source_origin_normalizes_programmatic_projection_metadata() -> None:
    generated = SourceDocument.from_text(
        PurePosixPath("out/generated.md"),
        "<!-- scieqlint-disable-next-line BAD999 -->\n# Heading\n",
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(
            source_document_id="  source/input.xml  ",
            source_kind="  jats-xml  ",
            conversion_stage="  translation  ",
        ),
    )

    result = check_documents(
        (generated,),
        config=Config(profile=ProfileConfig(name="generated-myst")),
    )

    diagnostic = next(item for item in result.diagnostics if item.code == "SUP001")
    assert dict(diagnostic.properties) == {
        "generated_document": "out/generated.md",
        "source_document": "source/input.xml",
        "source_kind": "jats-xml",
        "conversion_stage": "translation",
    }
    payload = json.loads(JsonReporter().render(result))
    projected = next(item for item in payload["diagnostics"] if item["code"] == "SUP001")
    assert projected["properties"] == dict(diagnostic.properties)


def test_source_origin_rejects_blank_programmatic_projection_metadata() -> None:
    with pytest.raises(ValueError, match="source_document_id must be a non-empty string"):
        SourceOrigin(source_document_id="   ")
    with pytest.raises(ValueError, match="source_kind must be a non-empty string"):
        SourceOrigin(source_document_id="source/input.xml", source_kind="   ")
    with pytest.raises(ValueError, match="conversion_stage must be a non-empty string"):
        SourceOrigin(source_document_id="source/input.xml", conversion_stage="\t")


def test_generated_provenance_facts_preserve_per_document_origin_metadata() -> None:
    generated = SourceDocument.from_text(
        PurePosixPath("out/generated.md"),
        "# Generated\n",
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(
            source_document_id="source/original.xml",
            source_kind="jats-xml",
            conversion_stage="xml-to-markdown",
            source_sha="abc123",
            tool="converter",
            tool_version="2.1",
            preserved_anchor_inventory=("energy",),
        ),
    )
    other_generated = SourceDocument.from_text(
        PurePosixPath("out/other.md"),
        "# Other\n",
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(
            source_document_id="source/other.tex",
            source_kind="latex",
            conversion_stage="translation",
        ),
    )

    supplied = _generated_provenance_facts(
        (generated, other_generated),
        Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="profile-default",
                conversion_stage="profile-default",
            )
        ),
    )
    unspecified = _generated_provenance_facts(
        (doc("out/unmapped.md", "# Unmapped\n"),),
        Config(profile=ProfileConfig(name="generated-myst")),
    )

    assert supplied == (
        GeneratedProvenanceFact(
            fact_id="out/generated.md::generated-provenance",
            document_id="out/generated.md",
            span=None,
            raw=None,
            confidence="generated",
            generated_document_id="out/generated.md",
            source_document_id="source/original.xml",
            source_kind="jats-xml",
            conversion_stage="xml-to-markdown",
            source_sha="abc123",
            tool="converter",
            tool_version="2.1",
            preserved_anchor_inventory=("energy",),
        ),
        GeneratedProvenanceFact(
            fact_id="out/other.md::generated-provenance",
            document_id="out/other.md",
            span=None,
            raw=None,
            confidence="generated",
            generated_document_id="out/other.md",
            source_document_id="source/other.tex",
            source_kind="latex",
            conversion_stage="translation",
        ),
    )
    assert unspecified == ()

    query = QueryHost(FactSnapshot(generated_provenance=supplied))
    assert query.generated.provenance() == supplied


def test_profile_annotations_do_not_create_source_identity() -> None:
    generated = SourceDocument.from_text(
        PurePosixPath("out/generated.md"),
        "# Generated\n",
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(source_document_id="source/original.xml"),
    )

    provenance = _generated_provenance_facts(
        (generated,),
        Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="profile-default",
                conversion_stage="profile-default",
            )
        ),
    )

    [origin] = provenance
    assert origin.source_document_id == "source/original.xml"
    assert origin.source_kind == "profile-default"
    assert origin.conversion_stage == "profile-default"


def test_generated_profile_rejects_duplicate_markdown_document_paths() -> None:
    duplicate = doc("out/generated.md", "# Generated\n")

    with pytest.raises(ValueError, match=r"^duplicate document path\(s\): out/generated\.md$"):
        check_documents(
            (duplicate, duplicate),
            config=Config(profile=ProfileConfig(name="generated-myst")),
        )


def test_generated_profile_rejects_duplicate_paths_across_document_kinds() -> None:
    generated = SourceDocument.from_text(
        PurePosixPath("same.md"),
        "# Generated\n",
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(source_document_id="source/input.xml"),
    )
    latex = SourceDocument.from_text(
        PurePosixPath("same.md"),
        r"\[x = 1\]",
        DocumentKind.LATEX,
    )

    with pytest.raises(ValueError, match=r"^duplicate document path\(s\): same\.md$"):
        check_documents(
            (generated, latex),
            config=Config(profile=ProfileConfig(name="generated-myst")),
        )


def test_default_profile_rejects_duplicate_document_paths() -> None:
    duplicate = doc("out/generated.md", "# Generated\n")

    with pytest.raises(ValueError, match=r"^duplicate document path\(s\): out/generated\.md$"):
        check_documents((duplicate, duplicate), config=Config())


@pytest.mark.parametrize("markdown_enabled", [True, False])
def test_suppression_diagnostic_is_projected_independently_of_scanning(
    markdown_enabled: bool,
) -> None:
    generated = SourceDocument.from_text(
        PurePosixPath("out/generated.md"),
        "<!-- scieqlint-disable-next-line BAD999 -->\n# Heading\n",
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(source_document_id="source/input.xml"),
    )

    result = check_documents(
        (generated,),
        config=Config(
            scanner=ScannerConfig(markdown=markdown_enabled),
            profile=ProfileConfig(name="generated-myst"),
        ),
    )

    diagnostic = next(item for item in result.diagnostics if item.code == "SUP001")
    assert diagnostic.profile == "generated-myst"
    assert diagnostic.provenance_ids == ("out/generated.md::generated-provenance",)
    assert dict(diagnostic.properties) == {
        "generated_document": "out/generated.md",
        "source_document": "source/input.xml",
    }
    payload = json.loads(JsonReporter().render(result))
    assert payload["schema_version"] == "0.2"
    projected = next(item for item in payload["diagnostics"] if item["code"] == "SUP001")
    assert projected["profile"] == "generated-myst"
    assert projected["provenance_ids"] == ["out/generated.md::generated-provenance"]
    assert projected["properties"] == {
        "generated_document": "out/generated.md",
        "source_document": "source/input.xml",
    }


def _provenance_diagnostic_result():
    source = doc("source/paper.md", "(energy)=\n## Energy\n")
    generated = SourceDocument.from_text(
        PurePosixPath("out/paper.md"),
        "## Energy\n",
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(
            source_document_id=source.path.as_posix(),
            tool="translator",
            preserved_anchor_inventory=("energy",),
        ),
    )
    return check_documents(
        (source, generated),
        config=Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="latex",
                conversion_stage="translation",
            )
        ),
    )


def test_generated_diagnostic_ir_references_provenance_and_schema_metadata() -> None:
    diagnostic = _provenance_diagnostic_result().diagnostics[0]
    projection = SchemaHost.project_diagnostic(diagnostic)

    assert projection.version == DIAGNOSTIC_PROJECTION_VERSION
    assert projection.profile == "generated-myst"
    assert projection.provenance_ids == ("out/paper.md::generated-provenance",)
    assert dict(projection.properties) == {
        "generated_document": "out/paper.md",
        "source_document": "source/paper.md",
        "source_kind": "latex",
        "conversion_stage": "translation",
    }
    assert diagnostic.profile == projection.profile
    assert diagnostic.provenance_ids == projection.provenance_ids
    assert diagnostic.properties == projection.properties


def test_generated_query_ignores_provenance_without_a_source_document() -> None:
    provenance = GeneratedProvenanceFact(
        fact_id="out/generated.md::generated-provenance",
        document_id="out/generated.md",
        span=None,
        raw=None,
        confidence="generated",
        generated_document_id="out/generated.md",
    )

    query = QueryHost(FactSnapshot(generated_provenance=(provenance,)))

    assert query.generated.dropped_targets() == ()


def test_generated_profile_leaves_unmapped_diagnostics_unannotated() -> None:
    result = check_documents(
        (
            doc(
                "out/unmapped.md",
                "# One\n# Two\nSee {eq}`missing-equation` and {ref}`missing-target`.\n",
            ),
        ),
        config=Config(profile=ProfileConfig(name="generated-myst")),
    )

    assert result.diagnostics
    assert all(diagnostic.profile is None for diagnostic in result.diagnostics)
    assert all(diagnostic.provenance_ids == () for diagnostic in result.diagnostics)
    assert all(diagnostic.properties == () for diagnostic in result.diagnostics)


def test_projection_keeps_ordinary_fact_ids_out_of_generated_provenance_lookup() -> None:
    origin = GeneratedProvenanceFact(
        fact_id="out/generated.md::generated-provenance",
        document_id="out/generated.md",
        span=None,
        confidence="generated",
        generated_document_id="out/generated.md",
        source_document_id="source/paper.md",
    )
    diagnostic = Diagnostic(
        code="REF010",
        severity=Severity.WARNING,
        message="duplicate code-cell target",
        span=SourceSpan(
            path=PurePosixPath("out/generated.md"),
            start=0,
            end=1,
            line=1,
            col=1,
            end_line=1,
            end_col=1,
        ),
        provenance_ids=("structure-cell-1",),
        properties=(("target", "cell"),),
    )

    projected = _project_generated_diagnostic(
        diagnostic,
        profile="generated-myst",
        generated_provenance_by_id={origin.fact_id: origin},
        generated_provenance_by_document={origin.generated_document_id: origin},
    )

    assert projected.profile == "generated-myst"
    assert projected.provenance_ids == (
        "structure-cell-1",
        "out/generated.md::generated-provenance",
    )
    assert projected.properties == (
        ("target", "cell"),
        ("generated_document", "out/generated.md"),
        ("source_document", "source/paper.md"),
    )


def test_json_reporter_uses_schema_host_names_for_multiple_origins() -> None:
    first = GeneratedProvenanceFact(
        fact_id="origin-a",
        document_id="out/generated.md",
        span=None,
        confidence="generated",
        generated_document_id="out/generated.md",
        source_document_id="source/a.xml",
        source_kind="jats-xml",
    )
    second = GeneratedProvenanceFact(
        fact_id="origin-b",
        document_id="out/generated.md",
        span=None,
        confidence="generated",
        generated_document_id="out/generated.md",
        source_document_id="source/b.tex",
        source_kind="latex",
    )
    projected = _project_generated_diagnostic(
        Diagnostic(
            code="GEN002",
            severity=Severity.WARNING,
            message="generated math contains suspicious formula text",
            span=None,
            profile="generated-myst",
            provenance_ids=(first.fact_id, second.fact_id),
            properties=(("formula_artifact_kind", "spaced-token"),),
        ),
        profile="generated-myst",
        generated_provenance_by_id={
            first.fact_id: first,
            second.fact_id: second,
        },
        generated_provenance_by_document={},
    )

    result = CheckResult(
        diagnostics=(projected,),
        files_checked=1,
        math_blocks_checked=0,
        config_path=None,
        version="1.1.0",
    )
    payload = json.loads(JsonReporter().render(result))

    assert payload["schema_version"] == "0.2"
    assert payload["diagnostics"][0]["properties"] == {
        "formula_artifact_kind": "spaced-token",
        "provenance_1_generated_document": "out/generated.md",
        "provenance_1_source_document": "source/a.xml",
        "provenance_1_source_kind": "jats-xml",
        "provenance_2_generated_document": "out/generated.md",
        "provenance_2_source_document": "source/b.tex",
        "provenance_2_source_kind": "latex",
    }


def test_projection_deduplicates_origins_and_owns_colliding_reporter_fields() -> None:
    origin = GeneratedProvenanceFact(
        fact_id="origin-a",
        document_id="out/generated.md",
        span=None,
        confidence="generated",
        generated_document_id="out/generated.md",
        source_document_id="source/paper.md",
    )
    projected = _project_generated_diagnostic(
        Diagnostic(
            code="GEN001",
            severity=Severity.WARNING,
            message="missing anchor",
            span=None,
            provenance_ids=(origin.fact_id, origin.fact_id),
            properties=(
                ("profile", "rule-profile"),
                ("provenanceIds", "rule-origin"),
                ("provenance", "rule-origin"),
                ("generated_document", "rule-document.md"),
            ),
        ),
        profile="generated-myst",
        generated_provenance_by_id={origin.fact_id: origin},
        generated_provenance_by_document={},
    )
    result = CheckResult(
        diagnostics=(projected,),
        files_checked=1,
        math_blocks_checked=0,
        config_path=None,
        version="1.1.0",
    )

    assert projected.provenance_ids == (origin.fact_id,)
    assert projected.properties == (
        ("generated_document", "out/generated.md"),
        ("source_document", "source/paper.md"),
    )
    assert not any(name.startswith("provenance_2_") for name, _value in projected.properties)

    json_diagnostic = json.loads(JsonReporter().render(result))["diagnostics"][0]
    assert json_diagnostic["profile"] == "generated-myst"
    assert json_diagnostic["provenance_ids"] == [origin.fact_id]
    assert json_diagnostic["properties"] == {
        "generated_document": "out/generated.md",
        "source_document": "source/paper.md",
    }

    sarif_properties = json.loads(SarifReporter().render(result))["runs"][0]["results"][0][
        "properties"
    ]
    assert sarif_properties == {
        "generated_document": "out/generated.md",
        "profile": "generated-myst",
        "provenanceIds": [origin.fact_id],
        "source_document": "source/paper.md",
    }

    text = TextReporter().render(result)
    github = GitHubReporter().render(result)
    for rendered in (text, github):
        assert rendered.count("profile") == 1
        assert rendered.count("provenance") == 1
        assert rendered.count("generated_document") == 1
        assert "rule-" not in rendered


def test_generated_profile_keeps_heterogeneous_origins_through_public_path() -> None:
    source_a = doc("source/a.md", "(energy)=\n## Energy\n")
    source_b = doc("source/b.md", "(force)=\n## Force\n")
    generated_a = SourceDocument.from_text(
        PurePosixPath("out/a.md"),
        "## Energy\n",
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(
            source_document_id=source_a.path.as_posix(),
            source_kind="jats-xml",
            conversion_stage="xml-to-markdown",
            preserved_anchor_inventory=("energy",),
        ),
    )
    generated_b = SourceDocument.from_text(
        PurePosixPath("out/b.md"),
        "## Force\n",
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(
            source_document_id=source_b.path.as_posix(),
            source_kind="latex",
            conversion_stage="translation",
            preserved_anchor_inventory=("force",),
        ),
    )

    result = check_documents(
        (source_a, source_b, generated_a, generated_b),
        config=Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="profile-default",
                conversion_stage="profile-default",
            )
        ),
    )

    assert {
        (
            diagnostic.detail,
            frozenset(diagnostic.properties),
        )
        for diagnostic in result.diagnostics
    } == {
        (
            "source anchor 'energy' from source/a.md is absent in out/a.md",
            frozenset(
                {
                    "generated_document": "out/a.md",
                    "source_document": "source/a.md",
                    "source_kind": "jats-xml",
                    "conversion_stage": "xml-to-markdown",
                }.items()
            ),
        ),
        (
            "source anchor 'force' from source/b.md is absent in out/b.md",
            frozenset(
                {
                    "generated_document": "out/b.md",
                    "source_document": "source/b.md",
                    "source_kind": "latex",
                    "conversion_stage": "translation",
                }.items()
            ),
        ),
    }


def test_json_sarif_and_github_project_provenance_without_source_rescanning() -> None:
    result = _provenance_diagnostic_result()

    json_payload = json.loads(JsonReporter().render(result))
    assert json_payload["schema_version"] == "0.2"
    json_diagnostic = json_payload["diagnostics"][0]
    assert json_diagnostic["profile"] == "generated-myst"
    assert json_diagnostic["provenance_ids"] == ["out/paper.md::generated-provenance"]
    assert json_diagnostic["properties"] == {
        "conversion_stage": "translation",
        "generated_document": "out/paper.md",
        "source_document": "source/paper.md",
        "source_kind": "latex",
    }

    sarif_payload = json.loads(SarifReporter().render(result))
    assert sarif_payload["runs"][0]["results"][0]["properties"] == {
        "conversion_stage": "translation",
        "generated_document": "out/paper.md",
        "profile": "generated-myst",
        "provenanceIds": ["out/paper.md::generated-provenance"],
        "source_document": "source/paper.md",
        "source_kind": "latex",
    }

    github = GitHubReporter().render(result)
    assert "conversion_stage=translation" in github
    assert "generated_document=out/paper.md" in github
    assert "source_kind=latex" in github
    assert "profile=generated-myst" in github
    assert "provenance=out/paper.md::generated-provenance" in github
