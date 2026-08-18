from __future__ import annotations

import json
from pathlib import PurePosixPath

from scieqlint.api import check_documents
from scieqlint.app import _generated_profile_snapshot
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.facts.generated import GeneratedProvenanceFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.query.host import QueryHost
from scieqlint.report.github import GitHubReporter
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def test_generated_profile_snapshot_preserves_per_document_origin_metadata() -> None:
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

    supplied = _generated_profile_snapshot(
        (generated, other_generated),
        Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="profile-default",
                conversion_stage="profile-default",
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
    assert unspecified.generated_provenance == ()

    query = QueryHost(supplied)
    assert query.generated.provenance_for_document("out/generated.md") == (
        supplied.generated_provenance[0],
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
