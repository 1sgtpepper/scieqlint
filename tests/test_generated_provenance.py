from __future__ import annotations

import json
from pathlib import PurePosixPath

from scieqlint.app import _generated_profile_snapshot
from scieqlint.api import check_documents
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.facts.generated import GeneratedProvenanceFact
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.query.host import QueryHost
from scieqlint.report.github import GitHubReporter
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def test_generated_profile_snapshot_preserves_only_caller_supplied_origin_metadata() -> None:
    generated = SourceDocument.from_text(
        PurePosixPath("out/generated.md"),
        "# Generated\n",
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(
            source_document_id="source/original.xml",
            source_sha="abc123",
            tool="converter",
            tool_version="2.1",
            preserved_anchor_inventory=("energy",),
        ),
    )

    supplied = _generated_profile_snapshot(
        (generated,),
        Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="jats-xml",
                conversion_stage="xml-to-markdown",
            )
        ),
    )
    unspecified = _generated_profile_snapshot(
        (doc("out/unmapped.md", "# Unmapped\n"),),
        Config(profile=ProfileConfig(name="generated-myst")),
    )

    assert supplied.generated_provenance == (
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
    )
    assert unspecified.generated_provenance == ()

    query = QueryHost(supplied)
    assert (
        query.generated.provenance_for_document("out/generated.md") == supplied.generated_provenance
    )
    assert query.generated.provenance_for_document("missing.md") == ()


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

    assert diagnostic.profile == "generated-myst"
    assert diagnostic.provenance_ids == ("out/paper.md::generated-provenance",)
    assert dict(diagnostic.properties) == {
        "generated_document": "out/paper.md",
        "source_document": "source/paper.md",
        "source_kind": "latex",
        "conversion_stage": "translation",
    }


def test_json_sarif_and_github_project_provenance_without_source_rescanning() -> None:
    result = _provenance_diagnostic_result()

    json_payload = json.loads(JsonReporter().render(result))
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
