from __future__ import annotations

import json
from pathlib import PurePosixPath

from scieqlint.diag.model import CheckResult, Severity, SourceSpan
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.facts.reference import CrossrefMetadataFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost
from scieqlint.report.json import JsonReporter


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def span(path: str, start: int = 0, end: int = 1) -> SourceSpan:
    return SourceSpan(
        path=PurePosixPath(path),
        start=start,
        end=end,
        line=1,
        col=start + 1,
        end_line=1,
        end_col=max(start + 1, end),
    )


def metadata(
    fact_id: str,
    *,
    document: str,
    boundary: str,
    kind: str,
    source_format: str,
    display: tuple[tuple[str, str], ...] = (),
) -> CrossrefMetadataFact:
    return CrossrefMetadataFact(
        fact_id=fact_id,
        document_id=document,
        span=span(document),
        raw=None,
        source_fact_id=f"{fact_id}-source",
        logical_target="energy",
        normalized_target="energy",
        reference_kind=kind,
        source_format=source_format,
        output_boundary=boundary,
        resolved_target_kind=kind,
        target_metadata=display,
        metadata_kind="target-definition",
        display_metadata=display,
        target_span=span(document),
    )


def test_myst_frontend_lowers_source_neutral_crossref_metadata() -> None:
    source = doc(
        "paper.md",
        "See {ref}`Energy balance <energy>` and {eq}`eq-energy`.\n",
    )

    snapshot = MySTFrontend().lower((source,))

    assert [fact.normalized_target for fact in snapshot.crossref_metadata] == [
        "energy",
        "eq-energy",
    ]
    generic, equation = snapshot.crossref_metadata
    assert generic.reference_kind == "ref"
    assert generic.reference_role == "ref"
    assert generic.metadata_kind == "reference-use"
    assert generic.source_format == "markdown"
    assert generic.output_boundary == "paper.md"
    assert generic.target_metadata == ()
    assert generic.display_metadata == (("display_text", "Energy balance"),)
    assert equation.reference_kind == "eq"
    assert equation.reference_role == "eq"
    assert equation.metadata_kind == "reference-use"
    assert equation.target_metadata == ()
    assert equation.display_metadata == (("reference_role", "eq"),)


def test_myst_frontend_produces_target_definitions_and_reference_engine_consumes_them() -> None:
    heading_target = doc("heading.md", "(shared)=\n# Shared heading\n")
    block_target = doc("block.md", "(shared)=\n```python\npass\n```\n")

    snapshot = MySTFrontend().lower((heading_target, block_target))
    definitions = tuple(
        fact for fact in snapshot.crossref_metadata if fact.metadata_kind == "target-definition"
    )
    diagnostics = ReferenceEngine().run(QueryHost(snapshot))

    assert [(fact.normalized_target, fact.resolved_target_kind) for fact in definitions] == [
        ("shared", "heading"),
        ("shared", "block"),
    ]
    conflicts = QueryHost(snapshot).references.conflicting_metadata()
    assert len(conflicts) == 1
    assert conflicts[0][0] == "shared"
    assert {fact.resolved_target_kind for fact in conflicts[0][1]} == {"heading", "block"}
    assert [diagnostic.code for diagnostic in diagnostics] == ["REF007"]


def test_query_reports_only_cross_boundary_metadata_conflicts() -> None:
    markdown = metadata(
        "m1",
        document="a.md",
        boundary="a.md",
        kind="ref",
        source_format="markdown",
        display=(("display_text", "Energy"),),
    )
    same = metadata(
        "m2",
        document="b.ipynb",
        boundary="b.ipynb#output-0",
        kind="ref",
        source_format="notebook",
        display=(("display_text", "Energy"),),
    )
    conflicting = metadata(
        "m3",
        document="c.md",
        boundary="custom-engine:c:0",
        kind="custom-figure",
        source_format="custom-engine",
        display=(("display_text", "Plot"),),
    )
    reference_use = (
        MySTFrontend()
        .lower((doc("use.md", "See {ref}`Local title <energy>`.\n"),))
        .crossref_metadata[0]
    )

    # Source format is provenance, not a semantic conflict by itself. The custom
    # output changes both the reference kind and display contract.
    query = QueryHost(FactSnapshot(crossref_metadata=(markdown, same, conflicting, reference_use)))
    conflicts = query.references.conflicting_metadata()

    assert conflicts == (("energy", (markdown, same, conflicting)),)
    diagnostics = ReferenceEngine().run(query)
    assert [diagnostic.code for diagnostic in diagnostics] == ["REF007"]
    assert diagnostics[0].span is not None
    assert diagnostics[0].span.path == PurePosixPath("c.md")
    assert diagnostics[0].provenance_ids == ("m1", "m3")
    assert diagnostics[0].properties == (
        ("target", "energy"),
        ("output_boundary", "custom-engine:c:0"),
        ("resolved_target_kind", "custom-figure"),
        ("source_format", "custom-engine"),
        ("canonical_boundary", "a.md"),
        ("canonical_resolved_target_kind", "ref"),
        ("canonical_source_format", "markdown"),
    )

    reversed_diagnostics = ReferenceEngine().run(
        QueryHost(FactSnapshot(crossref_metadata=(conflicting, same, markdown, reference_use)))
    )
    assert reversed_diagnostics == diagnostics


def test_same_semantic_metadata_across_source_formats_is_not_conflicting() -> None:
    markdown = metadata(
        "m1",
        document="a.md",
        boundary="a.md",
        kind="ref",
        source_format="markdown",
        display=(("display_text", "Energy"),),
    )
    notebook = metadata(
        "m2",
        document="b.ipynb",
        boundary="b.ipynb#output-0",
        kind="ref",
        source_format="notebook",
        display=(("display_text", "Energy"),),
    )

    query = QueryHost(FactSnapshot(crossref_metadata=(markdown, notebook)))

    assert query.references.conflicting_metadata() == ()
    assert ReferenceEngine().run(query) == ()


def test_display_metadata_key_order_is_not_a_conflict() -> None:
    first = metadata(
        "m1",
        document="a.md",
        boundary="a.md",
        kind="figure",
        source_format="markdown",
        display=(("caption", "Energy"), ("number", "1")),
    )
    second = metadata(
        "m2",
        document="b.ipynb",
        boundary="b.ipynb#output-0",
        kind="figure",
        source_format="notebook",
        display=(("number", "1"), ("caption", "Energy")),
    )

    query = QueryHost(FactSnapshot(crossref_metadata=(first, second)))

    assert query.references.conflicting_metadata() == ()
    assert ReferenceEngine().run(query) == ()


def test_same_metadata_in_distinct_boundaries_is_not_conflicting() -> None:
    first = metadata(
        "m1",
        document="a.md",
        boundary="engine:a",
        kind="figure",
        source_format="custom-engine",
    )
    second = metadata(
        "m2",
        document="b.md",
        boundary="engine:b",
        kind="figure",
        source_format="custom-engine",
    )

    query = QueryHost(FactSnapshot(crossref_metadata=(first, second)))

    assert query.references.conflicting_metadata() == ()
    assert ReferenceEngine().run(query) == ()


def test_json_report_projects_crossref_conflict_metadata_without_rescanning() -> None:
    canonical = metadata(
        "m1",
        document="a.md",
        boundary="a.md",
        kind="ref",
        source_format="markdown",
    )
    conflict = metadata(
        "m2",
        document="b.ipynb",
        boundary="b.ipynb#output-0",
        kind="figure",
        source_format="notebook",
    )
    diagnostic = (
        ReferenceEngine()
        .run(QueryHost(FactSnapshot(crossref_metadata=(canonical, conflict))))[0]
        .to_diagnostic()
    )

    payload = json.loads(
        JsonReporter().render(
            CheckResult(
                diagnostics=(diagnostic,),
                files_checked=2,
                math_blocks_checked=0,
                config_path=None,
                version="test",
            )
        )
    )

    projected = payload["diagnostics"][0]
    assert projected["code"] == "REF007"
    assert projected["severity"] == Severity.WARNING.value
    assert projected["provenance_ids"] == ["m1", "m2"]
    assert projected["properties"]["output_boundary"] == "b.ipynb#output-0"
