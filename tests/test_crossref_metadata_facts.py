from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

from scieqlint.api import check_documents
from scieqlint.app import _profile_snapshot
from scieqlint.config.model import AlgebraConfig, ChecksConfig, Config, ProfileConfig
from scieqlint.diag.model import CheckResult, Diagnostic, Severity, SourceSpan
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.facts.reference import CrossrefMetadataFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost
from scieqlint.report.json import JsonReporter


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def notebook(path: str, *cells: tuple[str, str | None]) -> SourceDocument:
    payload = {
        "cells": [
            {
                "cell_type": "code",
                "metadata": {
                    "label": label,
                    **({"fig-cap": caption} if caption is not None else {}),
                },
                "source": ["plot()\n"],
                "outputs": [
                    {
                        "output_type": "display_data",
                        "data": {"image/png": "encoded"},
                        "metadata": {},
                    }
                ],
            }
            for label, caption in cells
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return SourceDocument.from_text(
        PurePosixPath(path),
        json.dumps(payload),
        DocumentKind.NOTEBOOK,
    )


def cross_format_config() -> Config:
    return Config(
        profile=ProfileConfig(
            name="cross-format-references",
            output_profile="commonmark",
        ),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )


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
    logical_target: str = "energy",
    target_path: str | None = "energy.md",
    target_metadata: tuple[tuple[str, str], ...] = (),
) -> CrossrefMetadataFact:
    return CrossrefMetadataFact(
        fact_id=fact_id,
        document_id=document,
        span=span(document),
        raw=None,
        source_fact_id=f"{fact_id}-source",
        logical_target=logical_target,
        normalized_target=logical_target,
        source_format=source_format,
        output_boundary=boundary,
        resolved_target_kind=kind,
        normalized_target_path=(None if target_path is None else PurePosixPath(target_path)),
        target_metadata=target_metadata,
        metadata_kind="target-definition",
        target_span=span(document),
    )


def test_myst_frontend_lowers_source_neutral_crossref_metadata() -> None:
    source = doc(
        "paper.md",
        "See {ref}`Energy balance <energy>` and {eq}`eq-energy`.\n",
    )

    snapshot = MySTFrontend().lower((source,))
    query = QueryHost(snapshot)

    assert [fact.normalized_target for fact in snapshot.crossref_metadata] == [
        "energy",
        "eq-energy",
    ]
    generic, equation = snapshot.crossref_metadata
    assert generic.reference_role == "ref"
    assert generic.display_title == "Energy balance"
    assert generic.resolved_target_kind is None
    assert generic.metadata_kind == "reference-use"
    assert generic.source_format == "markdown"
    assert generic.output_boundary == "paper.md"
    assert generic.normalized_target_path is None
    assert generic.target_metadata == ()
    assert equation.reference_role == "eq"
    assert equation.display_title is None
    assert equation.resolved_target_kind is None
    assert equation.metadata_kind == "reference-use"
    assert equation.normalized_target_path is None
    assert equation.target_metadata == ()
    assert query.references.metadata_facts() == snapshot.crossref_metadata


def test_myst_frontend_preserves_equation_role_display_titles() -> None:
    source = doc(
        "paper.md",
        "See {eq}`Energy balance <eq-energy>` and {numref}`Eq. %s <eq-energy>`.\n",
    )

    snapshot = MySTFrontend().lower((source,))

    assert [(ref.ref_kind, ref.target, ref.title) for ref in snapshot.equation_refs] == [
        ("eq", "eq-energy", "Energy balance"),
        ("numref", "eq-energy", "Eq. %s"),
    ]
    assert [fact.display_title for fact in snapshot.crossref_metadata] == [
        "Energy balance",
        "Eq. %s",
    ]


def test_profile_adds_metadata_for_raw_equation_labels_and_references() -> None:
    source = doc(
        "raw.md",
        "\\begin{equation}\nx = 1 \\label{raw-energy}\nSee \\ref{raw-energy}\n\\end{equation}\n",
    )

    snapshot = _profile_snapshot((source,), cross_format_config())

    [label] = snapshot.equation_labels
    [reference] = snapshot.equation_refs
    label_metadata = next(
        fact for fact in snapshot.crossref_metadata if fact.source_fact_id == label.fact_id
    )
    reference_metadata = next(
        fact for fact in snapshot.crossref_metadata if fact.source_fact_id == reference.fact_id
    )
    assert label_metadata.metadata_kind == "target-definition"
    assert label_metadata.resolved_target_kind == "equation"
    assert label_metadata.normalized_target == "raw-energy"
    assert reference_metadata.metadata_kind == "reference-use"
    assert reference_metadata.reference_role == "tex-ref"
    assert reference_metadata.normalized_target == "raw-energy"
    assert label_metadata.target_span == label.label_span
    assert reference_metadata.target_span == reference.target_span


def test_myst_frontend_keeps_same_labels_in_distinct_member_identities() -> None:
    heading_target = doc("heading.md", "(shared)=\n# Shared heading\n")
    block_target = doc("block.md", "(shared)=\n```python\npass\n```\n")

    snapshot = MySTFrontend().lower((heading_target, block_target))
    definitions = tuple(
        fact for fact in snapshot.crossref_metadata if fact.metadata_kind == "target-definition"
    )
    query = QueryHost(snapshot)
    diagnostics = ReferenceEngine().run(query)

    assert [
        (fact.normalized_target_path, fact.normalized_target, fact.resolved_target_kind)
        for fact in definitions
    ] == [
        (PurePosixPath("heading.md"), "shared", "heading"),
        (PurePosixPath("block.md"), "shared", "block"),
    ]
    assert query.references.conflicting_metadata() == ()
    assert diagnostics == ()


def test_myst_frontend_binds_fragment_only_reference_to_its_source_member() -> None:
    source = doc("paper.md", "(shared)=\n# Shared\nSee [local](#shared).\n")

    snapshot = MySTFrontend().lower((source,))
    definitions = tuple(
        fact for fact in snapshot.crossref_metadata if fact.metadata_kind == "target-definition"
    )
    references = tuple(
        fact for fact in snapshot.crossref_metadata if fact.metadata_kind == "reference-use"
    )

    assert [(fact.normalized_target_path, fact.normalized_target) for fact in definitions] == [
        (PurePosixPath("paper.md"), "shared")
    ]
    assert [(fact.normalized_target_path, fact.normalized_target) for fact in references] == [
        (PurePosixPath("paper.md"), "shared")
    ]


def test_path_aware_metadata_identity_keeps_same_fragment_targets_separate() -> None:
    first = metadata(
        "m1",
        document="a.md",
        boundary="a.md",
        kind="heading",
        source_format="markdown",
        logical_target="shared",
        target_path="a.md",
    )
    second = metadata(
        "m2",
        document="b.md",
        boundary="b.md",
        kind="block",
        source_format="markdown",
        logical_target="shared",
        target_path="b.md",
    )

    query = QueryHost(FactSnapshot(crossref_metadata=(second, first)))

    assert query.references.conflicting_metadata() == ()
    assert ReferenceEngine().run(query) == ()


def test_path_aware_metadata_conflict_reports_complete_target_identity() -> None:
    canonical = metadata(
        "m1",
        document="a.md",
        boundary="a.md",
        kind="heading",
        source_format="markdown",
        logical_target="shared",
        target_path="chapter.md",
        target_metadata=(("placement", "before_heading"),),
    )
    conflict = metadata(
        "m2",
        document="b.ipynb",
        boundary="b.ipynb#output-0",
        kind="block",
        source_format="notebook",
        logical_target="shared",
        target_path="chapter.md",
        target_metadata=(("placement", "before_block"),),
    )

    query = QueryHost(FactSnapshot(crossref_metadata=(conflict, canonical)))

    assert query.references.conflicting_metadata() == (
        ((PurePosixPath("chapter.md"), "shared"), (canonical, conflict)),
    )
    diagnostics = ReferenceEngine().run(query)
    assert len(diagnostics) == 1
    assert diagnostics[0].message.endswith("chapter.md#shared")
    assert diagnostics[0].properties[0] == ("target", "chapter.md#shared")


def test_check_documents_does_not_merge_path_fragment_identity_boundaries() -> None:
    first = doc("a", "(b#c)=\n# Heading\n")
    second = doc("a#b", "(c)=\n```python\npass\n```\n")

    result = check_documents((first, second), config=cross_format_config())

    assert result.diagnostics == ()


def test_incomplete_target_definition_is_not_grouped_by_label() -> None:
    first = metadata(
        "m1",
        document="a.md",
        boundary="a.md",
        kind="heading",
        source_format="markdown",
        target_path=None,
    )
    second = metadata(
        "m2",
        document="b.md",
        boundary="b.md#output-0",
        kind="figure",
        source_format="notebook",
        target_path=None,
    )

    query = QueryHost(FactSnapshot(crossref_metadata=(first, second)))

    assert query.references.conflicting_metadata() == ()
    assert ReferenceEngine().run(query) == ()


def test_query_reports_only_cross_boundary_metadata_conflicts() -> None:
    markdown = metadata(
        "m1",
        document="a.md",
        boundary="a.md",
        kind="ref",
        source_format="markdown",
        target_metadata=(("caption", "Energy"),),
    )
    same = metadata(
        "m2",
        document="b.ipynb",
        boundary="b.ipynb#output-0",
        kind="ref",
        source_format="notebook",
        target_metadata=(("caption", "Energy"),),
    )
    conflicting = metadata(
        "m3",
        document="c.md",
        boundary="custom-engine:c:0",
        kind="custom-figure",
        source_format="custom-engine",
        target_metadata=(("caption", "Plot"),),
    )
    reference_use = (
        MySTFrontend()
        .lower((doc("use.md", "See {ref}`Local title <energy>`.\n"),))
        .crossref_metadata[0]
    )

    # Source format is provenance, not a semantic conflict by itself. The custom
    # output changes both the resolved target kind and target metadata.
    query = QueryHost(FactSnapshot(crossref_metadata=(markdown, same, conflicting, reference_use)))
    conflicts = query.references.conflicting_metadata()

    assert conflicts == (((PurePosixPath("energy.md"), "energy"), (markdown, same, conflicting)),)
    diagnostics = ReferenceEngine().run(query)
    assert [diagnostic.code for diagnostic in diagnostics] == ["REF007"]
    assert diagnostics[0].span is not None
    assert diagnostics[0].span.path == PurePosixPath("c.md")
    assert diagnostics[0].provenance_ids == ("m1", "m3")
    assert diagnostics[0].properties == (
        ("target", "energy.md#energy"),
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
        target_metadata=(("caption", "Energy"),),
    )
    notebook = metadata(
        "m2",
        document="b.ipynb",
        boundary="b.ipynb#output-0",
        kind="ref",
        source_format="notebook",
        target_metadata=(("caption", "Energy"),),
    )

    query = QueryHost(FactSnapshot(crossref_metadata=(markdown, notebook)))

    assert query.references.conflicting_metadata() == ()
    assert ReferenceEngine().run(query) == ()


def test_target_metadata_key_order_is_not_a_conflict() -> None:
    first = metadata(
        "m1",
        document="a.md",
        boundary="a.md",
        kind="figure",
        source_format="markdown",
        target_metadata=(("caption", "Energy"), ("number", "1")),
    )
    second = metadata(
        "m2",
        document="b.ipynb",
        boundary="b.ipynb#output-0",
        kind="figure",
        source_format="notebook",
        target_metadata=(("number", "1"), ("caption", "Energy")),
    )

    assert (
        first.target_metadata
        == second.target_metadata
        == (
            ("caption", "Energy"),
            ("number", "1"),
        )
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


def test_reference_use_titles_do_not_become_target_metadata_conflicts() -> None:
    documents = (
        doc("a.md", "See {ref}`Overview <fig-energy>` and {eq}`eq-energy`."),
        doc("b.md", "See {ref}`Energy balance <fig-energy>` and {eq}`eq-energy`."),
        notebook("producer.ipynb", ("fig-energy", "Energy"), ("eq-energy", None)),
    )

    result = check_documents(documents, config=cross_format_config())
    snapshot = _profile_snapshot(documents, cross_format_config())

    assert not any(item.code == "REF007" for item in result.diagnostics)
    assert [
        (
            fact.logical_target,
            fact.reference_role,
            fact.display_title,
            fact.normalized_target_path,
            fact.target_metadata,
        )
        for fact in snapshot.crossref_metadata
        if fact.metadata_kind == "reference-use"
    ] == [
        ("fig-energy", "ref", "Overview", None, ()),
        ("eq-energy", "eq", None, None, ()),
        ("fig-energy", "ref", "Energy balance", None, ()),
        ("eq-energy", "eq", None, None, ()),
    ]
    assert [
        (
            fact.logical_target,
            fact.resolved_target_kind,
            fact.normalized_target_path,
            fact.target_metadata,
        )
        for fact in snapshot.crossref_metadata
        if fact.metadata_kind == "target-definition"
    ] == [
        (
            "fig-energy",
            "figure",
            PurePosixPath("producer.ipynb"),
            (("fig-cap", "Energy"),),
        ),
        (
            "eq-energy",
            "equation",
            PurePosixPath("producer.ipynb"),
            (),
        ),
    ]


def test_notebook_member_paths_keep_equal_labels_separate() -> None:
    equivalent_documents = (
        notebook("a.ipynb", ("fig-shared", "Shared plot")),
        notebook("b.ipynb", ("fig-shared", "Shared plot")),
    )
    conflicting_documents = (
        notebook("a.ipynb", ("fig-shared", "Shared plot")),
        notebook("b.ipynb", ("fig-shared", "Different plot")),
    )
    equivalent = check_documents(equivalent_documents, config=cross_format_config())
    conflicting = check_documents(conflicting_documents, config=cross_format_config())
    equivalent_snapshot = _profile_snapshot(equivalent_documents, cross_format_config())
    conflicting_snapshot = _profile_snapshot(conflicting_documents, cross_format_config())

    assert not any(item.code == "REF007" for item in equivalent.diagnostics)
    assert not any(item.code == "REF007" for item in conflicting.diagnostics)
    assert [
        (
            fact.normalized_target_path,
            fact.logical_target,
            fact.resolved_target_kind,
            fact.target_metadata,
        )
        for fact in equivalent_snapshot.crossref_metadata
        if fact.metadata_kind == "target-definition"
    ] == [
        (
            PurePosixPath("a.ipynb"),
            "fig-shared",
            "figure",
            (("fig-cap", "Shared plot"),),
        ),
        (
            PurePosixPath("b.ipynb"),
            "fig-shared",
            "figure",
            (("fig-cap", "Shared plot"),),
        ),
    ]
    assert QueryHost(equivalent_snapshot).references.conflicting_metadata() == ()
    assert [
        (
            fact.normalized_target_path,
            fact.logical_target,
            fact.resolved_target_kind,
            fact.target_metadata,
        )
        for fact in conflicting_snapshot.crossref_metadata
        if fact.metadata_kind == "target-definition"
    ] == [
        (
            PurePosixPath("a.ipynb"),
            "fig-shared",
            "figure",
            (("fig-cap", "Shared plot"),),
        ),
        (
            PurePosixPath("b.ipynb"),
            "fig-shared",
            "figure",
            (("fig-cap", "Different plot"),),
        ),
    ]
    assert QueryHost(conflicting_snapshot).references.conflicting_metadata() == ()


@pytest.mark.public_regression
def test_public_check_documents_reports_notebook_output_metadata_conflict() -> None:
    def document(second_caption: str) -> SourceDocument:
        payload = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {"label": "fig-shared"},
                    "outputs": [
                        {
                            "data": {"image/png": "payload"},
                            "metadata": {"fig-cap": "Shared plot"},
                            "output_type": "display_data",
                        },
                        {
                            "data": {"image/png": "payload"},
                            "metadata": {"fig-cap": second_caption},
                            "output_type": "display_data",
                        },
                    ],
                    "source": [],
                }
            ],
            "metadata": {"language_info": {"name": "python"}},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        return SourceDocument.from_text(
            PurePosixPath("reachable.ipynb"),
            json.dumps(payload, sort_keys=True),
            DocumentKind.NOTEBOOK,
        )

    conflicting = document("Different plot")
    result = check_documents((conflicting,), config=cross_format_config())

    cell_start = conflicting.text.index('{"cell_type": "code"')
    cell_length = json.JSONDecoder().raw_decode(conflicting.text[cell_start:])[1]
    cell_end = cell_start + cell_length
    line, col = conflicting.line_index.position(cell_start)
    end_line, end_col = conflicting.line_index.position(cell_end - 1)
    expected_span = SourceSpan(
        path=conflicting.path,
        start=cell_start,
        end=cell_end,
        line=line,
        col=col,
        end_line=end_line,
        end_col=end_col,
        cell=0,
        cell_line=1,
    )
    canonical_boundary = "reachable.ipynb::notebook-cell::0::output::0"
    conflict_boundary = "reachable.ipynb::notebook-cell::0::output::1"
    assert result.diagnostics == (
        Diagnostic(
            code="REF007",
            severity=Severity.WARNING,
            message="conflicting cross-reference metadata: reachable.ipynb#fig-shared",
            span=expected_span,
            detail=(
                f"{conflict_boundary!r} reports kind='figure', format='notebook', "
                "metadata={'fig-cap': 'Different plot'}; canonical boundary "
                f"{canonical_boundary!r} reports kind='figure', format='notebook', "
                "metadata={'fig-cap': 'Shared plot'}"
            ),
            hint="Use consistent cross-reference metadata for this target.",
            rule="references.crossref_metadata_conflict",
            provenance_ids=(
                f"{canonical_boundary}::crossref-metadata",
                f"{conflict_boundary}::crossref-metadata",
            ),
            properties=(
                ("target", "reachable.ipynb#fig-shared"),
                ("output_boundary", conflict_boundary),
                ("resolved_target_kind", "figure"),
                ("source_format", "notebook"),
                ("canonical_boundary", canonical_boundary),
                ("canonical_resolved_target_kind", "figure"),
                ("canonical_source_format", "notebook"),
            ),
        ),
    )
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert result.exit_code() == 0

    equivalent = document("Shared plot")
    equivalent_result = check_documents((equivalent,), config=cross_format_config())
    assert equivalent_result.diagnostics == ()
    assert equivalent_result.files_checked == 1
    assert equivalent_result.math_blocks_checked == 0
    assert equivalent_result.exit_code() == 0


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
