from __future__ import annotations

import json
from pathlib import PurePosixPath

from scieqlint.api import check_documents
from scieqlint.app import _profile_snapshot
from scieqlint.config.model import AlgebraConfig, ChecksConfig, Config, ProfileConfig
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost
from scieqlint.report.json import JsonReporter


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def notebook(
    path: str,
    *,
    label: str | None = None,
    caption: str | None = None,
    output_metadata: dict[str, object] | None = None,
    markdown_source: str | None = None,
) -> SourceDocument:
    cells: list[dict[str, object]] = []
    if markdown_source is not None:
        cells.append({"cell_type": "markdown", "metadata": {}, "source": markdown_source})
    if label is not None:
        metadata: dict[str, object] = {"label": label}
        if caption is not None:
            metadata["fig-cap"] = caption
        cells.append(
            {
                "cell_type": "code",
                "metadata": metadata,
                "outputs": [
                    {
                        "data": {"image/png": "encoded"},
                        "metadata": output_metadata or {},
                        "output_type": "display_data",
                    }
                ],
                "source": ["plot()\n"],
            }
        )
    payload = {
        "cells": cells,
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return SourceDocument.from_text(
        PurePosixPath(path),
        json.dumps(payload, sort_keys=True),
        DocumentKind.NOTEBOOK,
    )


def cross_format_config() -> Config:
    return Config(
        profile=ProfileConfig(name="cross-format-references", output_profile="commonmark"),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )


def figure_markdown(path: str, caption: str, *, language: str = "python") -> SourceDocument:
    return doc(
        path,
        f"```{{code-cell}} {language}\n:label: fig-shared\n:fig-cap: {caption}\nplot()\n```\n",
    )


def test_reference_uses_are_not_target_metadata() -> None:
    source = doc(
        "paper.md",
        "See {ref}`Energy balance <energy>` and {eq}`eq-energy`.\n",
    )

    snapshot = MySTFrontend().lower((source,))
    query = QueryHost(snapshot)

    assert [ref.normalized_target for ref in snapshot.generic_refs] == ["energy"]
    assert [ref.normalized_target for ref in snapshot.equation_refs] == ["eq-energy"]
    assert snapshot.crossref_metadata == ()
    assert query.references.metadata_facts() == ()
    assert query.references.conflicting_metadata() == ()


def test_source_target_definitions_reach_the_conflict_diagnostic() -> None:
    heading_target = doc("heading.md", "(shared)=\n# Shared heading\n")
    block_target = doc("block.md", "(shared)=\n```python\npass\n```\n")

    snapshot = MySTFrontend().lower((heading_target, block_target))
    assert [fact.target_kind for fact in snapshot.crossref_metadata] == ["heading", "block"]

    result = check_documents((heading_target, block_target), config=cross_format_config())

    assert [item.code for item in result.diagnostics if item.code == "REF007"] == ["REF007"]


def test_markdown_notebook_and_custom_kernel_producers_share_one_query_path() -> None:
    documents = (
        figure_markdown("figure.md", "Shared plot"),
        notebook("figure.ipynb", label="fig-shared", caption="Shared plot"),
        figure_markdown("custom.md", "Shared plot", language="custom.kernel"),
    )

    snapshot = _profile_snapshot(documents, cross_format_config())
    result = check_documents(documents, config=cross_format_config())

    assert [fact.normalized_target for fact in snapshot.crossref_metadata] == [
        "fig-shared",
        "fig-shared",
        "fig-shared",
    ]
    assert {fact.source_format for fact in snapshot.crossref_metadata} == {
        "markdown",
        "notebook",
    }
    assert not any(item.code == "REF007" for item in result.diagnostics)


def test_output_metadata_changes_reachable_crossref_conflict_behavior() -> None:
    equivalent = (
        notebook(
            "a.ipynb",
            label="fig-shared",
            caption="Shared plot",
            output_metadata={"fig-cap": "Shared plot"},
        ),
        notebook(
            "b.ipynb",
            label="fig-shared",
            caption="Shared plot",
            output_metadata={"fig-cap": "Shared plot"},
        ),
    )
    conflicting = (
        equivalent[0],
        notebook(
            "b.ipynb",
            label="fig-shared",
            caption="Shared plot",
            output_metadata={"fig-cap": "Different plot"},
        ),
    )

    equivalent_result = check_documents(equivalent, config=cross_format_config())
    conflicting_result = check_documents(conflicting, config=cross_format_config())

    assert not any(item.code == "REF007" for item in equivalent_result.diagnostics)
    conflicts = [item for item in conflicting_result.diagnostics if item.code == "REF007"]
    assert len(conflicts) == 1
    assert "metadata={'fig-cap': 'Different plot'}" in (conflicts[0].detail or "")
    assert conflicts[0].span is not None
    assert conflicts[0].span.path == PurePosixPath("b.ipynb")


def test_notebook_markdown_references_feed_the_profile_fact_snapshot() -> None:
    document = notebook(
        "references.ipynb",
        markdown_source="$$\nx = 1\n$$ {#eq-notebook}\n\nSee {eq}`eq-notebook`.\n",
    )

    snapshot = _profile_snapshot((document,), cross_format_config())
    result = check_documents((document,), config=cross_format_config())

    assert [label.normalized_label for label in snapshot.equation_labels] == ["eq-notebook"]
    assert [reference.ref_kind for reference in snapshot.equation_refs] == ["eq"]
    assert snapshot.equation_refs[0].span is not None
    assert snapshot.equation_refs[0].span.cell == 0
    assert not any(item.code == "REF002" for item in result.diagnostics)
    assert [item.code for item in result.diagnostics if item.code == "PORT001"] == ["PORT001"]


def test_json_report_projects_source_reached_crossref_conflict() -> None:
    result = check_documents(
        (
            notebook("a.ipynb", label="fig-shared", caption="Shared plot"),
            notebook(
                "b.ipynb",
                label="fig-shared",
                caption="Shared plot",
                output_metadata={"fig-cap": "Different plot"},
            ),
        ),
        config=cross_format_config(),
    )

    payload = json.loads(JsonReporter().render(result))
    projected = [item for item in payload["diagnostics"] if item["code"] == "REF007"]

    assert len(projected) == 1
    assert projected[0]["properties"]["target"] == "fig-shared"
    assert projected[0]["properties"]["source_format"] == "notebook"
    assert projected[0]["provenance_ids"]
