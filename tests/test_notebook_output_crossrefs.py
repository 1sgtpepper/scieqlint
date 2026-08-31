from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path, PurePosixPath

import pytest

import scieqlint.frontend.notebook_input as notebook_input_module
from scieqlint.api import check_documents as public_check_documents
from scieqlint.app import _profile_snapshot, check_documents
from scieqlint.config.load import load_config
from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    ProfileConfig,
    ProjectConfig,
    ReferencesConfig,
    ValidationProfile,
)
from scieqlint.diag.model import Severity, SourceSpan
from scieqlint.engine.portability import PortabilityEngine
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.frontend.notebook import NotebookFrontend
from scieqlint.frontend.notebook_input import parse_notebook_input
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.io.workspace import WorkspaceHost
from scieqlint.parse.math import MathHost
from scieqlint.policy import PolicyHost
from scieqlint.query.host import QueryHost
from scieqlint.report.json import JsonReporter


def notebook(data: object, path: str = "theme.ipynb") -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath(path),
        json.dumps(data, sort_keys=True),
        DocumentKind.NOTEBOOK,
    )


def markdown(text: str, path: str = "theme.qmd") -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath(path),
        text,
        DocumentKind.MARKDOWN,
    )


def config(profile: ValidationProfile | None = "math-accessibility") -> Config:
    return Config(
        profile=ProfileConfig(name=profile),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )


def notebook_crossrefs_config() -> Config:
    return config("notebook-crossrefs")


def notebook_payload(*cells: object) -> dict[str, object]:
    return {
        "cells": list(cells),
        "metadata": {"kernelspec": {"language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def code_cell(
    *,
    metadata: object,
    outputs: object = (),
    source: object = "plot()",
) -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": metadata,
        "outputs": list(outputs) if isinstance(outputs, tuple) else outputs,
        "source": source,
    }


def display_output(
    *,
    output_metadata: object,
    mime_types: tuple[str, ...] = ("image/png",),
) -> dict[str, object]:
    return {
        "data": dict.fromkeys(mime_types, "payload"),
        "metadata": output_metadata,
        "output_type": "display_data",
    }


def test_notebook_frontend_lowers_cell_renderings_outputs_and_boundaries() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={
                    "quarto": {
                        "label": "fig-theme",
                        "fig-cap": "Theme comparison",
                        "renderings": ["light", "dark"],
                    },
                    "tags": ["hide-input"],
                },
                outputs=(
                    display_output(
                        output_metadata={"needs_background": "light"},
                        mime_types=("image/png", "text/plain"),
                    ),
                    display_output(
                        output_metadata={"needs_background": "dark"},
                    ),
                ),
                source=["plot_light()\n", "plot_dark()\n"],
            )
        )
    )

    snapshot = NotebookFrontend().lower((document,))

    [cell] = snapshot.code_cells
    assert cell.language == "python"
    assert cell.engine == "python"
    assert cell.label == "fig-theme"
    assert cell.tags == ("hide-input",)
    assert cell.raw == "plot_light()\nplot_dark()\n"
    assert cell.option_dict() == {
        "fig-cap": "Theme comparison",
        "label": "fig-theme",
        "renderings": '["light","dark"]',
        "tags": '["hide-input"]',
    }
    assert [output.output_index for output in snapshot.notebook_outputs] == [0, 1]
    assert snapshot.notebook_outputs[0] in snapshot.all_facts()
    assert QueryHost(snapshot).structure.notebook_outputs() == snapshot.notebook_outputs
    assert snapshot.notebook_outputs[0].mime_types == ("image/png", "text/plain")
    assert snapshot.notebook_outputs[0].metadata == (("needs_background", "light"),)
    assert all(output.span is not None for output in snapshot.notebook_outputs)
    assert [output.span.cell for output in snapshot.notebook_outputs if output.span] == [0, 0]
    assert all(
        output.span and output.span.cell_line is None for output in snapshot.notebook_outputs
    )
    assert all(
        output.raw is not None and document.text[output.span.start : output.span.end] == output.raw
        for output in snapshot.notebook_outputs
        if output.span is not None
    )
    assert [fact.output_boundary for fact in snapshot.crossref_metadata] == [
        "theme.ipynb::notebook-cell::0::output::0",
        "theme.ipynb::notebook-cell::0::output::1",
    ]
    assert [
        (fact.resolved_target_kind, fact.reference_role, fact.target_metadata)
        for fact in snapshot.crossref_metadata
    ] == [
        ("figure", None, (("fig-cap", "Theme comparison"),)),
        ("figure", None, (("fig-cap", "Theme comparison"),)),
    ]
    assert QueryHost(snapshot).references.conflicting_metadata() == ()


def test_notebook_frontend_can_exclude_markdown_without_dropping_code_facts() -> None:
    document = notebook(
        notebook_payload(
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "$$\nx = 1\n$$ {#equation}\n",
            },
            code_cell(metadata={}, source="x = 1"),
        )
    )

    snapshot = NotebookFrontend().lower((document,), _include_markdown=False)

    assert snapshot.documents == (document,)
    assert len(snapshot.code_cells) == 1
    assert snapshot.display_math == ()
    assert snapshot.equation_labels == ()


def test_notebook_output_spans_use_literal_boundaries_and_cell_identity() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("book/escaped-output.ipynb"),
        (
            "{\r\n"
            '  "cells": [\r\n'
            "    {\r\n"
            '      "cell_type": "code",\r\n'
            '      "metadata": {},\r\n'
            '      "outputs": [\r\n'
            r'        {"data": {"text/plain": "first\r\nline \"quoted\""}'
            r', "metadata": {}, "output_type": "display_data"},'
            "\r\n"
            r'        {"data": {"text/plain": "second"}'
            r', "metadata": {}, "output_type": "display_data"}'
            "\r\n"
            "      ],\r\n"
            '      "source": []\r\n'
            "    },\r\n"
            "    {\r\n"
            '      "cell_type": "code",\r\n'
            '      "metadata": {},\r\n'
            '      "outputs": [\r\n'
            r'        {"data": {"text/plain": "other-cell"}'
            r', "metadata": {}, "output_type": "execute_result"}'
            "\r\n"
            "      ],\r\n"
            '      "source": []\r\n'
            "    }\r\n"
            "  ],\r\n"
            '  "metadata": {},\r\n'
            '  "nbformat": 4,\r\n'
            '  "nbformat_minor": 5\r\n'
            "}\r\n"
        ),
        DocumentKind.NOTEBOOK,
    )

    snapshot = NotebookFrontend().lower((document,))

    assert [output.fact_id for output in snapshot.notebook_outputs] == [
        "book/escaped-output.ipynb::notebook-cell::0::output::0",
        "book/escaped-output.ipynb::notebook-cell::0::output::1",
        "book/escaped-output.ipynb::notebook-cell::1::output::0",
    ]
    assert [(output.cell_index, output.output_index) for output in snapshot.notebook_outputs] == [
        (0, 0),
        (0, 1),
        (1, 0),
    ]
    assert [output.output_type for output in snapshot.notebook_outputs] == [
        "display_data",
        "display_data",
        "execute_result",
    ]
    assert [output.document_id for output in snapshot.notebook_outputs] == [
        "book/escaped-output.ipynb",
        "book/escaped-output.ipynb",
        "book/escaped-output.ipynb",
    ]

    expected_output_texts = (
        (
            r'{"data": {"text/plain": "first\r\nline \"quoted\""}'
            r', "metadata": {}, "output_type": "display_data"}'
        ),
        (
            r'{"data": {"text/plain": "second"}'
            r', "metadata": {}, "output_type": "display_data"}'
        ),
        (
            r'{"data": {"text/plain": "other-cell"}'
            r', "metadata": {}, "output_type": "execute_result"}'
        ),
    )
    spans = tuple(output.span for output in snapshot.notebook_outputs)
    assert all(span is not None for span in spans)
    assert [span.path for span in spans if span is not None] == [
        PurePosixPath("book/escaped-output.ipynb"),
        PurePosixPath("book/escaped-output.ipynb"),
        PurePosixPath("book/escaped-output.ipynb"),
    ]
    assert [span.cell for span in spans if span is not None] == [0, 0, 1]
    assert [document.text[span.start : span.end] for span in spans if span is not None] == list(
        expected_output_texts
    )

    first_span, second_span, other_cell_span = (span for span in spans if span is not None)
    assert first_span.end < second_span.start < other_cell_span.start
    assert document.text[first_span.end : second_span.start] == ",\n        "


def test_notebook_profile_warns_once_for_renderings_with_crossref_options() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={
                    "label": "fig-theme",
                    "fig-cap": "Theme comparison",
                    "renderings": ["light", "dark"],
                },
                outputs=(display_output(output_metadata={}),),
                source='raise RuntimeError("must not execute")',
            )
        )
    )

    result = check_documents((document,), config=notebook_crossrefs_config())

    diagnostics = [item for item in result.diagnostics if item.code == "PORT004"]
    assert len(diagnostics) == 1
    [diagnostic] = diagnostics
    assert diagnostic.profile == "notebook-crossrefs"
    assert diagnostic.span is not None
    assert diagnostic.span.path == PurePosixPath("theme.ipynb")
    assert diagnostic.span.cell == 0
    assert diagnostic.span.cell_line == 1
    assert diagnostic.provenance_ids == ("theme.ipynb::notebook-cell::0",)
    assert dict(diagnostic.properties) == {
        "crossref_options": "label,fig-cap",
        "label": "fig-theme",
        "renderings": '["light","dark"]',
        "source_format": "notebook",
        "subject_fact_id": "theme.ipynb::notebook-cell::0",
    }

    payload = json.loads(JsonReporter().render(result))
    projected = [item for item in payload["diagnostics"] if item["code"] == "PORT004"]
    assert projected[0]["cell"] == 0
    assert projected[0]["properties"]["renderings"] == '["light","dark"]'


def test_notebook_source_cell_options_override_generated_metadata() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={
                    "label": "fig-stale",
                    "fig-cap": "Stale caption",
                    "renderings": ["single"],
                },
                source=(
                    "#| label: fig-source\n"
                    "#| fig-cap: Source caption\n"
                    "#| renderings: [light, dark]\n"
                    "#| unrelated: ignored\n"
                    "plot()\n"
                    "#| label: fig-late\n"
                ),
            )
        )
    )

    snapshot = NotebookFrontend().lower((document,))
    [cell] = snapshot.code_cells
    diagnostics = PortabilityEngine(
        profile="notebook-crossrefs",
        policy=PolicyHost(),
    ).run(QueryHost(snapshot))

    assert cell.label == "fig-source"
    assert cell.option_dict()["fig-cap"] == "Source caption"
    assert cell.option_dict()["renderings"] == "[light, dark]"
    assert "unrelated" not in cell.option_dict()
    assert [item.code for item in diagnostics] == ["PORT004"]


@pytest.mark.parametrize("label", ["fig-plot", "#tbl-table", "eq-energy", "#lst-listing"])
def test_portability_accepts_normalized_lowercase_crossref_prefixes(label: str) -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={
                    "label": label,
                    "fig-cap": "Plot",
                    "renderings": ["light", "dark"],
                }
            )
        )
    )
    snapshot = NotebookFrontend().lower((document,))
    query = QueryHost(snapshot)

    [cell] = snapshot.code_cells
    assert query.portability.quarto_crossref_label_issues() == ()
    assert query.portability.renderings_with_crossref_options() == (cell,)
    [conflict] = query.portability.notebook_rendering_conflicts()
    assert conflict.cell is cell


def test_portability_keeps_uppercase_label_prefixes_untyped() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={
                    "label": "FIG-plot",
                    "fig-cap": "Plot",
                    "renderings": ["light", "dark"],
                }
            )
        )
    )
    snapshot = NotebookFrontend().lower((document,))
    query = QueryHost(snapshot)

    [cell] = snapshot.code_cells
    assert query.portability.quarto_crossref_label_issues() == (cell,)
    [conflict] = query.portability.notebook_rendering_conflicts()
    assert conflict.crossref_options == ("fig-cap",)


def test_portability_keeps_unprefixed_crossref_labels_as_issues() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={
                    "label": "plot",
                    "fig-cap": "Plot",
                    "renderings": ["light", "dark"],
                }
            )
        )
    )
    snapshot = NotebookFrontend().lower((document,))
    query = QueryHost(snapshot)

    [cell] = snapshot.code_cells
    assert query.portability.quarto_crossref_label_issues() == (cell,)
    assert query.portability.renderings_with_crossref_options() == (cell,)
    assert len(query.portability.notebook_rendering_conflicts()) == 1


@pytest.mark.parametrize("visibility", ["hidden", "excluded"])
def test_portability_ignores_nonvisible_quarto_crossref_cells(visibility: str) -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={
                    "label": "plot",
                    "fig-cap": "Plot",
                    "renderings": ["light", "dark"],
                }
            )
        )
    )
    snapshot = NotebookFrontend().lower((document,))
    [cell] = snapshot.code_cells
    nonvisible_snapshot = replace(
        snapshot,
        code_cells=(replace(cell, visibility=visibility),),
    )

    query = QueryHost(nonvisible_snapshot).portability

    assert query.quarto_crossref_label_issues() == ()
    assert query.renderings_with_crossref_options() == ()
    assert query.notebook_rendering_conflicts() == ()


@pytest.mark.parametrize("visibility", ["hidden", "excluded"])
def test_public_visibility_suppresses_nonvisible_notebook_portability_cells(
    visibility: str,
) -> None:
    visible_payload = notebook_payload(
        code_cell(
            metadata={
                "label": "plot",
                "fig-cap": "Visible figure",
                "renderings": ["light", "dark"],
            }
        ),
        code_cell(
            metadata={"renderings": ["light", "dark"]},
            outputs=(display_output(output_metadata={"fig-cap": "Visible output"}),),
        ),
    )
    hidden_payload = notebook_payload(
        code_cell(
            metadata={
                "label": "plot",
                "fig-cap": "Hidden figure",
                "renderings": ["light", "dark"],
            }
        ),
        code_cell(
            metadata={"renderings": ["light", "dark"]},
            outputs=(display_output(output_metadata={"fig-cap": "Hidden output"}),),
        ),
    )
    visible = notebook(visible_payload, "visible.ipynb")
    hidden = notebook(hidden_payload, "hidden.ipynb")
    result = public_check_documents(
        (visible, hidden),
        config=Config(
            profile=ProfileConfig(name="notebook-crossrefs"),
            checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
            project=ProjectConfig(visibility=(("hidden.ipynb", visibility),)),
        ),
    )
    assert result.files_checked == 2
    assert result.math_blocks_checked == 0
    assert result.exit_code() == 0

    def source_range(document: SourceDocument, value: object) -> tuple[int, int]:
        raw = json.dumps(value, sort_keys=True)
        start = document.text.index(raw)
        return start, start + len(raw)

    cell_start, cell_end = source_range(visible, visible_payload["cells"][0])
    output_start, output_end = source_range(
        visible,
        visible_payload["cells"][1]["outputs"][0],
    )

    def diagnostic_signature(item) -> tuple[object, ...]:
        span = item.span
        assert span is not None
        return (
            item.code,
            item.severity.value,
            item.message,
            span.path,
            span.start,
            span.end,
            span.line,
            span.col,
            span.end_line,
            span.end_col,
            span.cell,
            span.cell_line,
            visible.text[span.start : span.end],
            item.equation,
            item.detail,
            item.hint,
            item.rule,
            item.suppressed,
            item.suppression_reason,
            item.profile,
            item.provenance_ids,
            item.properties,
        )

    assert [diagnostic_signature(item) for item in result.diagnostics] == [
        (
            "PORT004",
            "warning",
            "cell renderings are incompatible with cross-reference options",
            PurePosixPath("visible.ipynb"),
            cell_start,
            cell_end,
            1,
            cell_start + 1,
            1,
            cell_end,
            0,
            1,
            visible.text[cell_start:cell_end],
            None,
            "cell 'plot' combines renderings='[\"light\",\"dark\"]' with ['fig-cap']",
            (
                "Keep renderings on a cell without cross-reference options, or move "
                "the labeled figure/table structure outside the rendered cell."
            ),
            "portability.notebook_renderings_crossref",
            False,
            None,
            "notebook-crossrefs",
            ("visible.ipynb::notebook-cell::0",),
            (
                ("label", "plot"),
                ("renderings", '["light","dark"]'),
                ("crossref_options", "fig-cap"),
                ("source_format", "notebook"),
                ("subject_fact_id", "visible.ipynb::notebook-cell::0"),
            ),
        ),
        (
            "PORT004",
            "warning",
            "cell renderings are incompatible with cross-reference options",
            PurePosixPath("visible.ipynb"),
            output_start,
            output_end,
            1,
            output_start + 1,
            1,
            output_end,
            1,
            None,
            visible.text[output_start:output_end],
            None,
            (
                "cell '<caption-only cell>' at output 0 combines "
                "renderings='[\"light\",\"dark\"]' with ['fig-cap']"
            ),
            (
                "Keep renderings on a cell without cross-reference options, or move "
                "the labeled figure/table structure outside the rendered cell."
            ),
            "portability.notebook_renderings_crossref",
            False,
            None,
            "notebook-crossrefs",
            (
                "visible.ipynb::notebook-cell::1",
                "visible.ipynb::notebook-cell::1::output::0",
            ),
            (
                ("label", "<caption-only cell>"),
                ("renderings", '["light","dark"]'),
                ("crossref_options", "fig-cap"),
                ("source_format", "notebook"),
                ("subject_fact_id", "visible.ipynb::notebook-cell::1"),
                ("output_index", "0"),
            ),
        ),
    ]


def test_portability_normalizes_output_crossref_markers_once() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={"renderings": ["light", "dark"]},
                outputs=(
                    display_output(output_metadata={"label": "#fig-output", "fig-cap": "Plot"}),
                ),
            )
        )
    )
    snapshot = NotebookFrontend().lower((document,))
    query = QueryHost(snapshot)

    [cell] = snapshot.code_cells
    assert query.portability.renderings_with_crossref_options() == (cell,)
    assert query.portability.quarto_crossref_label_issues() == ()
    [conflict] = query.portability.notebook_rendering_conflicts()
    assert conflict.crossref_options == ("label", "fig-cap")
    assert conflict.output is snapshot.notebook_outputs[0]


def test_renderings_and_crossrefs_are_valid_when_not_combined() -> None:
    document = notebook(
        notebook_payload(
            code_cell(metadata={"renderings": ["light", "dark"]}),
            code_cell(metadata={"label": "fig-static", "fig-cap": "Static"}),
            code_cell(metadata={"label": "theme", "renderings": ["light", "dark"]}),
        )
    )

    result = check_documents((document,), config=notebook_crossrefs_config())

    assert [item for item in result.diagnostics if item.code == "PORT004"] == []


def test_caption_only_crossref_option_conflicts_with_renderings() -> None:
    document = notebook(
        notebook_payload(
            code_cell(metadata={"tbl-cap": "Summary", "renderings": ["light", "dark"]})
        )
    )

    snapshot = _profile_snapshot((document,), notebook_crossrefs_config())
    conflicts = QueryHost(snapshot).portability.notebook_rendering_conflicts()
    diagnostics = PortabilityEngine(
        profile="notebook-crossrefs",
        policy=PolicyHost(),
    ).run(QueryHost(snapshot))

    assert len(conflicts) == 1
    assert conflicts[0].crossref_options == ("tbl-cap",)
    assert [item.code for item in diagnostics] == ["PORT004"]
    assert dict(diagnostics[0].properties)["label"] == "<caption-only cell>"


def test_output_metadata_is_a_rendering_conflict_input_with_an_exact_location() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={"label": "fig-rendered", "renderings": ["light", "dark"]},
                outputs=(display_output(output_metadata={"fig-cap": "Rendered figure"}),),
            )
        )
    )

    snapshot = _profile_snapshot((document,), notebook_crossrefs_config())
    conflicts = QueryHost(snapshot).portability.notebook_rendering_conflicts()
    diagnostics = PortabilityEngine(
        profile="notebook-crossrefs",
        policy=PolicyHost(),
    ).run(QueryHost(snapshot))

    assert len(conflicts) == 1
    assert conflicts[0].output is snapshot.notebook_outputs[0]
    assert conflicts[0].crossref_options == ("label", "fig-cap")
    assert diagnostics[0].span == snapshot.notebook_outputs[0].span
    assert diagnostics[0].provenance_ids == (
        snapshot.code_cells[0].fact_id,
        snapshot.notebook_outputs[0].fact_id,
    )
    assert dict(diagnostics[0].properties)["output_index"] == "0"
    [metadata] = snapshot.crossref_metadata
    assert metadata.target_metadata == (("fig-cap", "Rendered figure"),)
    assert metadata.span == snapshot.notebook_outputs[0].span
    assert metadata.raw == snapshot.notebook_outputs[0].raw


def test_notebook_output_label_produces_target_metadata_without_cell_label() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={"renderings": ["light", "dark"]},
                outputs=(
                    display_output(
                        output_metadata={"label": "fig-output", "fig-cap": "Output caption"}
                    ),
                ),
            )
        )
    )

    snapshot = NotebookFrontend().lower((document,))

    [metadata] = snapshot.crossref_metadata
    [anchor] = snapshot.target_anchors
    output = snapshot.notebook_outputs[0]
    assert anchor.label == "fig-output"
    assert anchor.normalized_label == "fig-output"
    assert anchor.target_kind == "figure"
    assert anchor.attaches_to_fact_id == output.fact_id
    assert anchor.span == output.span
    assert anchor.label_span is not None
    assert document.text[anchor.label_span.start : anchor.label_span.end] == "fig-output"
    assert QueryHost(snapshot).references.target_index()["fig-output"] == (anchor,)
    assert metadata.logical_target == "fig-output"
    assert metadata.resolved_target_kind == "figure"
    assert metadata.metadata_kind == "target-definition"
    assert metadata.target_metadata == (("fig-cap", "Output caption"),)
    assert metadata.normalized_target_path == PurePosixPath("theme.ipynb")
    assert metadata.span == output.span
    assert metadata.target_span == anchor.label_span
    assert metadata.span is not None
    assert document.text[metadata.span.start : metadata.span.end] == output.raw
    identity = (PurePosixPath("theme.ipynb"), "fig-output")
    assert QueryHost(snapshot).references.target_identity_index()[identity] == (anchor,)


@pytest.mark.parametrize(
    ("caption_key", "expected_kind"),
    [
        ("fig-cap", "figure"),
        ("fig-subcap", "figure"),
        ("tbl-cap", "table"),
        ("tbl-subcap", "table"),
        ("lst-cap", "listing"),
        ("cap", "block"),
        ("caption", "block"),
    ],
)
def test_notebook_output_caption_metadata_infers_kind_without_typed_label(
    caption_key: str,
    expected_kind: str,
) -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={},
                outputs=(
                    display_output(
                        output_metadata={"label": "plain-output", caption_key: "Caption"}
                    ),
                ),
            ),
            {"cell_type": "markdown", "metadata": {}, "source": "See [](#plain-output).\n"},
        )
    )
    profile = Config(
        profile=ProfileConfig(name="reference-display"),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )

    snapshot = NotebookFrontend().lower((document,))
    [anchor] = snapshot.target_anchors
    [metadata] = [
        fact for fact in snapshot.crossref_metadata if fact.metadata_kind == "target-definition"
    ]
    result = public_check_documents((document,), config=profile)

    assert anchor.target_kind == expected_kind
    assert metadata.resolved_target_kind == expected_kind
    [diagnostic] = [item for item in result.diagnostics if item.code == "REF009"]
    assert dict(diagnostic.properties)["target_type"] == expected_kind


def test_notebook_output_target_prefixes_remain_case_sensitive() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={},
                outputs=(display_output(output_metadata={"label": "FIG-output"}),),
            )
        )
    )

    snapshot = NotebookFrontend().lower((document,))

    [anchor] = snapshot.target_anchors
    assert anchor.label == "FIG-output"
    assert anchor.target_kind is None
    assert snapshot.crossref_metadata == ()


@pytest.mark.public_regression
def test_notebook_output_listing_alias_resolves_and_preserves_label_span() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={},
                outputs=(
                    display_output(
                        output_metadata={
                            "lst-cap": "Output listing",
                            "lst-label": "lst-output",
                        }
                    ),
                ),
            ),
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "See {ref}`lst-output`.\n",
            },
        )
    )

    result = public_check_documents((document,), config=config("math-accessibility"))

    assert result.diagnostics == ()
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert result.exit_code() == 0

    snapshot = NotebookFrontend().lower((document,))
    query = QueryHost(snapshot)

    assert len(snapshot.notebook_outputs) == 1
    assert len(snapshot.target_anchors) == 1
    [output] = snapshot.notebook_outputs
    [anchor] = snapshot.target_anchors
    definitions = tuple(
        fact for fact in snapshot.crossref_metadata if fact.metadata_kind == "target-definition"
    )
    assert len(definitions) == 1
    [metadata] = definitions
    assert dict(output.metadata) == {"lst-cap": "Output listing", "lst-label": "lst-output"}
    assert anchor.label == "lst-output"
    assert anchor.target_kind == "listing"
    assert anchor.label_span is not None
    label_start = document.text.index('"lst-label": "lst-output"') + len('"lst-label": "')
    assert (anchor.label_span.start, anchor.label_span.end) == (
        label_start,
        label_start + len("lst-output"),
    )
    assert document.text[anchor.label_span.start : anchor.label_span.end] == "lst-output"
    assert metadata.logical_target == "lst-output"
    assert metadata.target_metadata == (("lst-cap", "Output listing"),)
    assert metadata.target_span == anchor.label_span
    assert query.references.target_index()["lst-output"] == (anchor,)
    assert query.references.unresolved_generic_refs() == ()
    assert ReferenceEngine().run(query) == ()


def test_notebook_output_label_precedes_listing_alias() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={},
                outputs=(
                    display_output(
                        output_metadata={
                            "label": "fig-canonical",
                            "lst-label": "lst-alias",
                        }
                    ),
                ),
            ),
        )
    )

    snapshot = NotebookFrontend().lower((document,))

    [anchor] = snapshot.target_anchors
    [metadata] = snapshot.crossref_metadata
    assert anchor.label == "fig-canonical"
    assert anchor.label_span is not None
    assert document.text[anchor.label_span.start : anchor.label_span.end] == "fig-canonical"
    assert metadata.logical_target == "fig-canonical"
    assert metadata.target_span == anchor.label_span


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"label": "ordinary", "lst-label": "lst-unused"}, ()),
        ({"label": "ordinary"}, ()),
        ({"label": "fig-primary", "lst-label": "lst-unused"}, ("label",)),
        ({"lst-label": "lst-only"}, ("lst-label",)),
        ({"label": " ", "lst-label": "lst-only"}, ("lst-label",)),
    ],
)
def test_renderings_use_the_effective_output_label(metadata, expected) -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={"renderings": ["light", "dark"]},
                outputs=(display_output(output_metadata=metadata),),
            )
        )
    )

    result = public_check_documents((document,), config=notebook_crossrefs_config())
    diagnostics = [d for d in result.diagnostics if d.code == "PORT004"]

    assert [dict(d.properties)["crossref_options"] for d in diagnostics] == (
        [",".join(expected)] if expected else []
    )


@pytest.mark.parametrize("kind", ["markdown", "notebook"])
@pytest.mark.parametrize("label", ["fig-theme", "'fig-theme'", '"fig-theme"'])
def test_renderings_preserve_quoted_source_label_meaning(kind: str, label: str) -> None:
    source = f"#| label: {label}\n#| renderings: [light, dark]\nplot()\n"
    document = (
        markdown(f"```python\n{source}```\n")
        if kind == "markdown"
        else notebook(notebook_payload(code_cell(metadata={}, source=source)))
    )

    result = public_check_documents((document,), config=notebook_crossrefs_config())
    [diagnostic] = [d for d in result.diagnostics if d.code == "PORT004"]

    assert dict(diagnostic.properties)["label"] == "fig-theme"
    assert diagnostic.span is not None
    assert diagnostic.span.path == document.path


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("'fig-it''s'", "fig-it's"),
        ("''", ""),
        ('""', ""),
        ("'fig-open", "'fig-open"),
        ('"fig-open', '"fig-open'),
        (r'"fig-\u0078"', r'"fig-\u0078"'),
        ("'fig-x' trailing", "'fig-x' trailing"),
    ],
)
def test_source_scalar_normalization_preserves_unsupported_forms(value: str, expected: str) -> None:
    document = notebook(
        notebook_payload(code_cell(metadata={}, source=f"#| label: {value}\nplot()\n"))
    )

    [cell] = NotebookFrontend().lower((document,)).code_cells

    assert cell.option_dict()["label"] == expected


@pytest.mark.parametrize("size", [255, 256, 257, 600])
@pytest.mark.parametrize("output_count", [1, 3])
def test_renderings_preview_is_bounded_without_losing_outputs(size: int, output_count: int) -> None:
    renderings = "x" * size
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={"renderings": renderings},
                outputs=tuple(
                    display_output(output_metadata={"label": f"fig-{index}"})
                    for index in range(output_count)
                ),
            )
        )
    )
    snapshot = NotebookFrontend().lower((document,))
    assert snapshot.code_cells[0].option_dict()["renderings"] == renderings
    result = public_check_documents((document,), config=notebook_crossrefs_config())
    diagnostics = [d for d in result.diagnostics if d.code == "PORT004"]

    assert len(diagnostics) == output_count
    assert [dict(d.properties)["output_index"] for d in diagnostics] == [
        str(index) for index in range(output_count)
    ]
    expected = renderings if size <= 256 else renderings[:253] + "..."
    for diagnostic in diagnostics:
        assert dict(diagnostic.properties)["renderings"] == expected
        assert f"renderings={expected!r}" in (diagnostic.detail or "")


@pytest.mark.public_regression
def test_notebook_output_listing_aliases_participate_in_duplicate_resolution() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={},
                outputs=(display_output(output_metadata={"lst-label": "lst-output"}),),
            ),
            code_cell(
                metadata={},
                outputs=(display_output(output_metadata={"lst-label": "lst-output"}),),
            ),
            {"cell_type": "markdown", "metadata": {}, "source": "See {ref}`lst-output`.\n"},
        )
    )

    result = public_check_documents((document,), config=config("math-accessibility"))

    assert len(result.diagnostics) == 1
    [diagnostic] = result.diagnostics
    assert (
        diagnostic.code,
        diagnostic.severity,
        diagnostic.message,
        diagnostic.equation,
        diagnostic.detail,
        diagnostic.hint,
        diagnostic.rule,
        diagnostic.suppressed,
        diagnostic.suppression_reason,
        diagnostic.profile,
        diagnostic.provenance_ids,
        diagnostic.properties,
    ) == (
        "REF005",
        Severity.WARNING,
        "ambiguous generic reference target: lst-output",
        None,
        "reference text: {ref}`lst-output`",
        None,
        "references.generic_target_ambiguous",
        False,
        None,
        None,
        (),
        (),
    )
    assert diagnostic.span is not None
    assert (diagnostic.span.path, diagnostic.span.cell, diagnostic.span.cell_line) == (
        document.path,
        2,
        1,
    )
    target_start = document.text.rindex("lst-output")
    assert (diagnostic.span.start, diagnostic.span.end) == (
        target_start,
        target_start + len("lst-output"),
    )
    assert document.text[diagnostic.span.start : diagnostic.span.end] == "lst-output"
    assert [
        document.text[start:end]
        for segment in diagnostic.span.segments
        for start, end in segment.ranges
    ] == list("lst-output")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert result.exit_code() == 0

    snapshot = NotebookFrontend().lower((document,))
    query = QueryHost(snapshot)
    identity = (PurePosixPath("theme.ipynb"), "lst-output")

    anchors = query.references.target_identity_index().get(identity, ())
    assert len(anchors) == 2
    assert query.references.duplicate_generic_targets()[identity] == anchors
    [reference] = query.references.ambiguous_generic_refs()
    assert reference.normalized_target == "lst-output"
    assert any(item.code == "REF005" for item in ReferenceEngine().run(query))


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("lst-label", "lst-code"),
        ("fig-subcap", ["left", "right"]),
        ("tbl-subcap", True),
    ],
)
def test_portability_recognizes_quarto_crossref_option_aliases(
    option: str,
    value: object,
) -> None:
    document = notebook(
        notebook_payload(code_cell(metadata={"renderings": ["light", "dark"], option: value}))
    )

    snapshot = NotebookFrontend().lower((document,))
    [conflict] = QueryHost(snapshot).portability.notebook_rendering_conflicts()

    assert conflict.output is None
    assert conflict.crossref_options == (option,)
    assert [
        item.code
        for item in check_documents(
            (document,),
            config=notebook_crossrefs_config(),
        ).diagnostics
    ] == ["PORT004"]


def test_portability_ignores_unprefixed_listing_label_alias() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={
                    "lst-label": "source",
                    "renderings": ["light", "dark"],
                }
            )
        )
    )

    result = check_documents((document,), config=notebook_crossrefs_config())

    assert not any(item.code == "PORT004" for item in result.diagnostics)


@pytest.mark.parametrize("option", ["fig-alt", "fig-align", "fig-width", "tbl-colwidths"])
def test_portability_ignores_non_crossref_quarto_options(option: str) -> None:
    document = notebook(
        notebook_payload(code_cell(metadata={"renderings": ["light", "dark"], option: "value"}))
    )

    result = check_documents((document,), config=notebook_crossrefs_config())

    assert not any(item.code == "PORT004" for item in result.diagnostics)


def test_output_crossref_aliases_keep_their_output_identity() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={"renderings": ["light", "dark"]},
                outputs=(
                    display_output(
                        output_metadata={"lst-label": "lst-first", "lst-cap": "First listing"}
                    ),
                    display_output(output_metadata={"fig-subcap": ["a", "b"]}),
                ),
            )
        )
    )

    snapshot = _profile_snapshot((document,), notebook_crossrefs_config())
    conflicts = QueryHost(snapshot).portability.notebook_rendering_conflicts()

    assert [
        (conflict.output.output_index, conflict.crossref_options) for conflict in conflicts
    ] == [
        (0, ("lst-label", "lst-cap")),
        (1, ("fig-subcap",)),
    ]


def test_notebook_frontend_ignores_nonmarkdown_and_malformed_markdown_cells() -> None:
    document = notebook(
        notebook_payload(
            "not a cell",
            {"cell_type": "raw", "metadata": {}, "source": "raw text"},
            {"cell_type": "markdown", "metadata": {}},
            code_cell(metadata={"label": "fig-code"}),
        )
    )

    snapshot = NotebookFrontend().lower((document,))

    assert len(snapshot.code_cells) == 1
    assert snapshot.code_cells[0].label == "fig-code"
    assert snapshot.target_anchors == ()
    assert snapshot.generic_refs == ()
    assert snapshot.equation_labels == ()
    assert snapshot.equation_refs == ()


def test_notebook_output_label_spans_preserve_json_unicode_escapes() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={},
                outputs=(display_output(output_metadata={"label": "fig-😀"}),),
            )
        )
    )

    snapshot = NotebookFrontend().lower((document,))

    [anchor] = snapshot.target_anchors
    assert anchor.label == "fig-😀"
    assert anchor.label_span is not None
    assert (
        document.text[anchor.label_span.start : anchor.label_span.end] == json.dumps("fig-😀")[1:-1]
    )


def test_large_output_label_span_does_not_materialize_decoded_char_ranges(monkeypatch) -> None:
    label = "fig-" + "x" * 100_000
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={},
                outputs=(display_output(output_metadata={"label": label}),),
            )
        )
    )

    def fail_if_materialized(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("output label spans do not need decoded character ranges")

    monkeypatch.setattr(
        notebook_input_module,
        "json_string_character_ranges",
        fail_if_materialized,
        raising=False,
    )
    snapshot = NotebookFrontend().lower((document,))

    [anchor] = snapshot.target_anchors
    assert anchor.label == label
    assert anchor.label_span is not None
    assert document.text[anchor.label_span.start : anchor.label_span.end] == label


def test_notebook_frontend_preserves_configured_project_member_identity() -> None:
    source = notebook(
        notebook_payload(
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "See [target](target.ipynb#target).\n",
            }
        ),
        "book/source.ipynb",
    )
    target = notebook(
        notebook_payload(
            {"cell_type": "markdown", "metadata": {}, "source": "(target)=\n# Target\n"}
        ),
        "book/target.ipynb",
    )
    snapshot = NotebookFrontend(workspace=WorkspaceHost(project_root=PurePosixPath("book"))).lower(
        (source, target)
    )

    assert tuple(member.normalized_path for member in snapshot.project_members) == (
        PurePosixPath("source.ipynb"),
        PurePosixPath("target.ipynb"),
    )
    assert QueryHost(snapshot).references.unresolved_generic_refs() == ()


def test_public_output_link_reports_only_the_missing_control() -> None:
    document = notebook(
        notebook_payload(
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "See [](#fig-output) and [](#missing-output).\n",
            },
            code_cell(
                metadata={},
                outputs=(display_output(output_metadata={"label": "fig-output"}),),
            ),
        )
    )

    result = public_check_documents((document,), config=config())

    [missing] = result.diagnostics
    assert (
        missing.code,
        missing.severity,
        missing.message,
        missing.equation,
        missing.detail,
        missing.hint,
        missing.rule,
        missing.suppressed,
        missing.suppression_reason,
        missing.profile,
        missing.provenance_ids,
        missing.properties,
    ) == (
        "REF002",
        Severity.WARNING,
        "equation reference target not found: missing-output",
        None,
        "reference text: [](#missing-output)",
        None,
        "references",
        False,
        None,
        None,
        (),
        (),
    )
    assert missing.span is not None
    assert (missing.span.path, missing.span.cell, missing.span.cell_line) == (
        document.path,
        0,
        1,
    )
    target_start = document.text.index("missing-output")
    assert (missing.span.start, missing.span.end) == (
        target_start,
        target_start + len("missing-output"),
    )
    assert document.text[missing.span.start : missing.span.end] == "missing-output"
    assert [
        document.text[start:end]
        for segment in missing.span.segments
        for start, end in segment.ranges
    ] == list("missing-output")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert result.exit_code() == 0


def test_notebook_display_resolution_aggregates_cross_cell_targets() -> None:
    document = notebook(
        notebook_payload(
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "See [](#fig-cell), [](#fig-output), and [](#missing-output).\n",
            },
            code_cell(
                metadata={"label": "fig-cell", "fig-cap": "Cell plot"},
                outputs=(
                    display_output(output_metadata={"label": "fig-output", "fig-cap": "Plot"}),
                ),
            ),
        )
    )

    snapshot = NotebookFrontend().lower((document,))

    by_target = {fact.normalized_target: fact for fact in snapshot.reference_display_text}
    [cell] = snapshot.code_cells
    [output_anchor] = [
        anchor for anchor in snapshot.target_anchors if anchor.normalized_label == "fig-output"
    ]
    resolved_cell = by_target["fig-cell"]
    resolved = by_target["fig-output"]
    unresolved = by_target["missing-output"]
    assert resolved_cell.target_type == "figure"
    assert resolved_cell.target_fact_ids == (cell.fact_id,)
    assert resolved_cell.target_identity == (PurePosixPath("theme.ipynb"), "fig-cell")
    assert resolved.target_type == "figure"
    assert resolved.target_fact_ids == (output_anchor.fact_id,)
    assert resolved.target_identity == (PurePosixPath("theme.ipynb"), "fig-output")
    assert unresolved.target_fact_ids == ()
    assert unresolved.target_identity is None


def test_nested_notebook_equation_refs_keep_cell_owned_source_blocks() -> None:
    document = notebook(
        notebook_payload(
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "$$\nx = 1 \\label{eq-first} \\ref{eq-first}\n$$\n",
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "$$\nx = 2 \\label{eq-second} \\ref{eq-second}\n$$\n",
            },
        )
    )

    snapshot = NotebookFrontend().lower((document,))

    labels = {label.normalized_label: label for label in snapshot.equation_labels}
    refs = {reference.normalized_target: reference for reference in snapshot.equation_refs}
    assert labels["eq-first"].source_block_id == refs["eq-first"].source_block_id
    assert labels["eq-second"].source_block_id == refs["eq-second"].source_block_id
    assert labels["eq-first"].source_block_id != labels["eq-second"].source_block_id
    assert labels["eq-first"].source_block_id.startswith("theme.ipynb::notebook-cell::0::")
    assert labels["eq-second"].source_block_id.startswith("theme.ipynb::notebook-cell::1::")


def test_notebook_output_labels_participate_in_duplicate_resolution() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={},
                outputs=(display_output(output_metadata={"label": "fig-output"}),),
            ),
            code_cell(
                metadata={},
                outputs=(display_output(output_metadata={"label": "fig-output"}),),
            ),
            {"cell_type": "markdown", "metadata": {}, "source": "See {ref}`fig-output`.\n"},
        )
    )

    snapshot = NotebookFrontend().lower((document,))
    query = QueryHost(snapshot)
    identity = (PurePosixPath("theme.ipynb"), "fig-output")

    anchors = query.references.target_identity_index()[identity]
    assert len(anchors) == 2
    assert query.references.duplicate_generic_targets()[identity] == anchors
    [reference] = query.references.ambiguous_generic_refs()
    assert reference.normalized_target == "fig-output"
    assert any(item.code == "REF005" for item in ReferenceEngine().run(query))


def test_untyped_notebook_output_label_is_an_ordinary_target() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={},
                outputs=(display_output(output_metadata={"label": "plain-output"}),),
            ),
            {"cell_type": "markdown", "metadata": {}, "source": "See {ref}`plain-output`.\n"},
        )
    )

    snapshot = NotebookFrontend().lower((document,))
    query = QueryHost(snapshot)

    [anchor] = snapshot.target_anchors
    assert anchor.target_kind is None
    assert query.references.target_index()["plain-output"] == (anchor,)
    assert not any(
        fact.metadata_kind == "target-definition" and fact.logical_target == "plain-output"
        for fact in snapshot.crossref_metadata
    )
    assert ReferenceEngine().run(query) == ()


def test_notebook_markdown_references_feed_the_profile_fact_snapshot() -> None:
    document = notebook(
        notebook_payload(
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "$$\nx = 1\n$$ {#eq-notebook}\n\nSee {eq}`eq-notebook`.\n",
            }
        )
    )

    snapshot = _profile_snapshot((document,), config())

    assert [label.normalized_label for label in snapshot.equation_labels] == ["eq-notebook"]
    assert [reference.ref_kind for reference in snapshot.equation_refs] == ["eq"]
    assert snapshot.equation_refs[0].span is not None
    assert snapshot.equation_refs[0].span.cell == 0


def test_notebook_profile_composition_preserves_cross_boundary_cell_facts() -> None:
    document = notebook(
        notebook_payload(
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["$$\nx = ", "1\n$$\nSee {eq}`missing`.\n"],
            }
        )
    )

    snapshot = _profile_snapshot((document,), config())
    result = check_documents((document,), config=config())

    assert len(snapshot.display_math) == 1
    assert snapshot.equation_labels == ()
    assert [reference.normalized_target for reference in snapshot.equation_refs] == ["missing"]
    assert snapshot.portability == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]
    [diagnostic] = result.diagnostics
    assert diagnostic.span is not None
    assert diagnostic.span.cell == 0
    assert diagnostic.span.segments
    assert document.text[diagnostic.span.start : diagnostic.span.end] == "missing"


def test_notebook_profile_reports_split_missing_generic_ref_once() -> None:
    document = notebook(
        notebook_payload(
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "(known)=\n# Known\nSee {ref}`known`.\n",
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["See {", "ref}`missing`.\n"],
            },
        )
    )

    snapshot = _profile_snapshot((document,), config())
    result = check_documents((document,), config=config())

    assert [reference.normalized_target for reference in snapshot.generic_refs] == [
        "known",
        "missing",
    ]
    [diagnostic] = result.diagnostics
    assert diagnostic.code == "REF004"
    assert diagnostic.detail == "reference text: {ref}`missing`"
    assert diagnostic.span is not None
    assert diagnostic.span.path == document.path
    assert diagnostic.span.cell == 1
    assert diagnostic.span.segments
    assert document.text[diagnostic.span.start : diagnostic.span.end] == "missing"


def test_notebook_frontend_keeps_crlf_inside_one_source_string() -> None:
    document = notebook(
        notebook_payload({"cell_type": "markdown", "metadata": {}, "source": "$$x\r\ny$$"})
    )

    snapshot = NotebookFrontend().lower((document,))

    [display] = snapshot.display_math
    assert display.span is not None
    assert document.text[display.span.start : display.span.end] == r"x\r\ny"
    assert display.span.cell == 0


def test_notebook_frontend_preserves_split_crlf_source_items() -> None:
    document = notebook(
        notebook_payload({"cell_type": "markdown", "metadata": {}, "source": ["$$x\r", "\ny$$"]})
    )

    snapshot = NotebookFrontend().lower((document,))

    [display] = snapshot.display_math
    assert display.body == "x\ny"
    assert display.span is not None
    assert display.span.cell == 0
    assert display.span.segments
    assert len(display.span.segments[1].ranges) == 2
    assert snapshot.unknown_math == ()
    assert snapshot.target_anchors == ()
    assert snapshot.generic_refs == ()
    assert snapshot.equation_labels == ()
    assert snapshot.equation_refs == ()
    assert snapshot.crossref_metadata == ()


def test_notebook_profile_keeps_inline_math_identity_distinct_per_cell() -> None:
    document = notebook(
        notebook_payload(
            {"cell_type": "markdown", "metadata": {}, "source": "Use $x$.\n"},
            {"cell_type": "markdown", "metadata": {}, "source": "Again $x$.\n"},
        ),
        path="accessible-math.ipynb",
    )

    snapshot = _profile_snapshot((document,), config())

    assert [fact.accessibility_id for fact in snapshot.inline_math] == [
        "accessible-math.ipynb::notebook-cell::0::inline-math::dollar::x",
        "accessible-math.ipynb::notebook-cell::1::inline-math::dollar::x",
    ]


def test_notebook_plain_text_math_has_no_accessibility_identity() -> None:
    document = notebook(
        notebook_payload({"cell_type": "markdown", "metadata": {}, "source": "compact a = b+c."})
    )

    snapshot = NotebookFrontend().lower((document,))

    [fact] = snapshot.inline_math
    assert fact.delimiter_kind == "plain-text"
    assert fact.body == "a = b+c"
    assert fact.accessibility_id is None


def test_public_math_accessibility_profile_lowers_notebook_inline_math_and_metadata() -> None:
    document = notebook(
        notebook_payload(
            {"cell_type": "markdown", "metadata": {}, "source": "Use $x$.\n"},
            {"cell_type": "markdown", "metadata": {}, "source": "Again $x$.\n"},
        ),
        path="accessible-math.ipynb",
    )
    accessibility_config = Config(
        profile=ProfileConfig(name="math-accessibility"),
        checks=ChecksConfig(
            algebra=AlgebraConfig(enabled=False),
            references=ReferencesConfig(enabled=False),
        ),
    )

    missing = public_check_documents((document,), config=accessibility_config)
    missing_diagnostics = tuple(
        diagnostic for diagnostic in missing.diagnostics if diagnostic.code == "PORT002"
    )
    subject_fact_ids = [
        dict(diagnostic.properties)["subject_fact_id"] for diagnostic in missing_diagnostics
    ]
    accessibility_ids = (
        "accessible-math.ipynb::notebook-cell::0::inline-math::dollar::x",
        "accessible-math.ipynb::notebook-cell::1::inline-math::dollar::x",
    )

    assert [diagnostic.code for diagnostic in missing.diagnostics] == ["PORT002", "PORT002"]
    assert [diagnostic.span.cell for diagnostic in missing_diagnostics if diagnostic.span] == [0, 1]
    assert len(subject_fact_ids) == 2
    assert len(set(subject_fact_ids)) == 2
    assert all(
        f"accessible-math.ipynb::notebook-cell::{cell}::" in subject_fact_id
        for cell, subject_fact_id in enumerate(subject_fact_ids)
    )

    accessible = public_check_documents(
        (document,),
        config=accessibility_config,
        accessibility_metadata={
            accessibility_ids[0]: "the variable x in cell 0",
            accessibility_ids[1]: "the variable x in cell 1",
        },
    )

    assert accessible.diagnostics == ()


def test_notebook_markdown_preserves_targets_metadata_display_and_json_spans() -> None:
    source = (
        "(fig-cell)=\n"
        "# Figure\n\n"
        "$$\n"
        "x = 1\n"
        "$$ {#eq-cell}\n\n"
        "See {ref}`Figure <fig-cell>` and {eq}`Equation <eq-cell>`.\n"
    )
    document = notebook(
        notebook_payload({"cell_type": "markdown", "metadata": {}, "source": source})
    )

    snapshot = NotebookFrontend().lower((document,))

    [anchor] = snapshot.target_anchors
    [generic_ref] = snapshot.generic_refs
    [equation_label] = snapshot.equation_labels
    [equation_ref] = snapshot.equation_refs
    assert anchor.fact_id.startswith("theme.ipynb::notebook-cell::0::")
    assert generic_ref.title == "Figure"
    assert generic_ref.target == "fig-cell"
    assert equation_label.label == "eq-cell"
    assert equation_ref.title == "Equation"
    assert equation_ref.target == "eq-cell"
    assert {(fact.metadata_kind, fact.logical_target) for fact in snapshot.crossref_metadata} == {
        ("target-definition", "fig-cell"),
        ("target-definition", "eq-cell"),
        ("reference-use", "fig-cell"),
        ("reference-use", "eq-cell"),
    }

    def source_slice(span: SourceSpan | None) -> str:
        assert span is not None
        assert span.cell == 0
        assert span.cell_line is not None
        return document.text[span.start : span.end]

    for span, expected in (
        (anchor.span, "(fig-cell)="),
        (generic_ref.span, "{ref}`Figure <fig-cell>`"),
        (generic_ref.role_span, "{ref}`Figure <fig-cell>`"),
        (equation_label.span, "eq-cell"),
        (equation_ref.span, "{eq}`Equation <eq-cell>`"),
        (equation_ref.role_span, "{eq}`Equation <eq-cell>`"),
    ):
        assert expected in source_slice(span)
    assert source_slice(anchor.label_span) == "fig-cell"
    assert source_slice(generic_ref.target_span) == "fig-cell"
    assert source_slice(equation_label.label_span) == "eq-cell"
    assert source_slice(equation_ref.target_span) == "eq-cell"

    for fact in snapshot.crossref_metadata:
        assert fact.logical_target in source_slice(fact.span)
        assert source_slice(fact.target_span) == fact.logical_target

    generic_metadata = next(
        fact
        for fact in snapshot.crossref_metadata
        if fact.metadata_kind == "reference-use" and fact.logical_target == "fig-cell"
    )
    assert generic_metadata.reference_role == "ref"
    assert generic_metadata.resolved_target_kind is None
    assert generic_metadata.target_metadata == ()
    assert generic_metadata.target_span is not None
    assert document.text[generic_metadata.target_span.start : generic_metadata.target_span.end] == (
        "fig-cell"
    )
    [display] = [
        fact for fact in snapshot.reference_display_text if fact.normalized_target == "fig-cell"
    ]
    assert display.source_fact_id == generic_ref.fact_id
    assert display.target_fact_ids == (anchor.fact_id,)
    assert display.target_identity == (PurePosixPath("theme.ipynb"), "fig-cell")
    assert display.explicit_text == "Figure"
    assert source_slice(display.display_text_span) == "Figure"


def test_markdown_executable_cells_use_the_same_policy_surface() -> None:
    document = markdown(
        "```python\n"
        "#| label: fig-theme\n"
        "#| fig-cap: Theme comparison\n"
        "#| renderings: [light, dark]\n"
        "plot()\n"
        "```\n"
    )

    result = check_documents((document,), config=notebook_crossrefs_config())

    [diagnostic] = [item for item in result.diagnostics if item.code == "PORT004"]
    assert diagnostic.span is not None
    assert diagnostic.span.cell is None
    assert dict(diagnostic.properties)["source_format"] == "markdown"


def test_notebook_renderings_profile_is_opt_in() -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={
                    "label": "fig-theme",
                    "fig-cap": "Theme comparison",
                    "renderings": ["light", "dark"],
                },
                outputs=(display_output(output_metadata={}),),
                source='raise RuntimeError("must not execute")',
            ),
        )
    )

    default_result = check_documents((document,), config=config(None))
    profile_result = check_documents((document,), config=notebook_crossrefs_config())

    assert [item.code for item in default_result.diagnostics if item.code == "PORT004"] == []
    assert [item.code for item in profile_result.diagnostics if item.code == "PORT004"] == [
        "PORT004"
    ]


@pytest.mark.parametrize(
    ("label", "expected", "raw_value"),
    [
        (True, "true", "true"),
        (7, "7", "7"),
        (["figure", 2], '["figure",2]', '["figure", 2]'),
    ],
)
def test_notebook_output_metadata_normalizes_scalar_labels(
    label: object,
    expected: str,
    raw_value: str,
) -> None:
    document = notebook(
        notebook_payload(
            code_cell(
                metadata={},
                outputs=(display_output(output_metadata={"label": label}),),
            )
        )
    )

    snapshot = NotebookFrontend().lower((document,))

    [output] = snapshot.notebook_outputs
    assert dict(output.metadata)["label"] == expected
    [anchor] = snapshot.target_anchors
    assert anchor.label == expected
    assert anchor.normalized_label == expected
    assert anchor.target_kind is None
    assert anchor.label_span is not None
    assert document.text[anchor.label_span.start : anchor.label_span.end] == raw_value


def test_notebook_frontend_bounds_malformed_cell_and_output_metadata() -> None:
    document = notebook(
        notebook_payload(
            {"cell_type": "code", "metadata": [], "outputs": [None, "bad"], "source": 7},
            code_cell(
                metadata={
                    "label": "fig-theme",
                    "fig-cap": "Theme comparison",
                    "renderings": {"light": True},
                },
                outputs="not-a-list",
            ),
            code_cell(
                metadata={"cap": ["caption", {"unsupported": True}]},
                outputs=(
                    display_output(output_metadata=[]),
                    display_output(
                        output_metadata={
                            "fig-cap": {"unsupported": True},
                            "label": ["fig-theme", {"unsupported": True}],
                        }
                    ),
                    {"data": {}, "metadata": {}},
                ),
                source=["plot()", 7],
            ),
        )
    )

    snapshot = NotebookFrontend().lower((document,))

    assert [(cell.label, cell.raw, cell.option_dict()) for cell in snapshot.code_cells] == [
        (None, None, {}),
        (
            "fig-theme",
            "plot()",
            {"fig-cap": "Theme comparison", "label": "fig-theme"},
        ),
        (None, None, {}),
    ]
    assert [
        (output.cell_index, output.output_index, output.output_type, output.metadata)
        for output in snapshot.notebook_outputs
    ] == [
        (2, 0, "display_data", ()),
        (2, 1, "display_data", ()),
        (2, 2, "unknown", ()),
    ]


def test_notebook_frontend_rejects_non_notebook_documents() -> None:
    with pytest.raises(ValueError, match="requires notebook documents"):
        NotebookFrontend().lower((markdown("# not a notebook\n"),))


@pytest.mark.parametrize("text", ["{", "[]", '{"cells": {}}'])
def test_notebook_frontend_bounds_invalid_json_roots_and_cell_collections(text: str) -> None:
    document = SourceDocument.from_text(
        PurePosixPath("malformed.ipynb"),
        text,
        DocumentKind.NOTEBOOK,
    )

    snapshot = NotebookFrontend().lower((document,))

    assert snapshot.documents == (document,)
    assert snapshot.code_cells == ()
    assert snapshot.notebook_outputs == ()


def test_notebook_frontend_skips_non_cell_entries_and_normalizes_scalar_metadata() -> None:
    document = notebook(
        notebook_payload(
            "not a cell",
            {"cell_type": "markdown", "metadata": {}, "source": "text"},
            code_cell(
                metadata={
                    "tags": " hide-input, remove-output ",
                    "fig-cap": True,
                    "caption": 3.5,
                    "renderings": [1, 2.5],
                    "label": {"unsupported": True},
                }
            ),
        )
    )

    snapshot = NotebookFrontend().lower((document,))

    assert len(snapshot.code_cells) == 1
    [cell] = snapshot.code_cells
    assert cell.label is None
    assert cell.tags == ("hide-input", "remove-output")
    assert cell.option_dict() == {
        "caption": "3.5",
        "fig-cap": "true",
        "renderings": "[1,2.5]",
        "tags": "hide-input, remove-output",
    }


def test_notebook_frontend_uses_no_language_for_invalid_kernel_metadata() -> None:
    document = notebook(
        {
            "cells": [code_cell(metadata={})],
            "metadata": {
                "kernelspec": {"language": 17},
                "language_info": {"name": "   "},
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
    )

    snapshot = NotebookFrontend().lower((document,))

    assert snapshot.code_cells[0].language is None


def test_notebook_facts_fixture_preserves_spans_without_executing_code() -> None:
    fixture = Path(__file__).parent / "fixtures" / "good" / "notebook_facts.ipynb"
    document = SourceDocument.from_text(
        PurePosixPath("notebook_facts.ipynb"),
        fixture.read_text(encoding="utf-8"),
        DocumentKind.NOTEBOOK,
    )

    snapshot = NotebookFrontend().lower((document,))

    [cell] = snapshot.code_cells
    [output] = snapshot.notebook_outputs
    assert cell.fact_id == "notebook_facts.ipynb::notebook-cell::1"
    assert cell.label == "fig-facts"
    assert cell.tags == ("hide-input",)
    assert cell.raw == "raise RuntimeError('not executed')\n"
    assert output.output_index == 0
    assert output.output_type == "display_data"
    assert output.mime_types == ("image/png",)
    assert dict(output.metadata) == {"label": "fig-output"}
    assert output.span is not None
    assert output.raw is not None
    assert document.text[output.span.start : output.span.end] == output.raw
    [anchor] = snapshot.target_anchors
    assert anchor.label == "fig-output"
    assert anchor.label_span is not None
    assert document.text[anchor.label_span.start : anchor.label_span.end] == "fig-output"

    default_result = public_check_documents((document,), config=Config())
    assert default_result.diagnostics == ()

    profile_result = public_check_documents((document,), config=config())
    assert [diagnostic.code for diagnostic in profile_result.diagnostics] == ["PORT002"]


def test_notebook_generated_formula_identity_uses_logical_cell_offsets() -> None:
    source = ["$$\n\\ f ", "r a c{x}{y}\r", "\n$$\n"]
    payload = notebook_payload(
        {"cell_type": "markdown", "metadata": {}, "source": source},
    )
    documents = tuple(
        SourceDocument.from_text(
            PurePosixPath("generated.ipynb"),
            json.dumps(payload, **options),
            DocumentKind.NOTEBOOK,
        )
        for options in ({}, {"indent": 2})
    )

    formula_ids: list[str] = []
    for document in documents:
        snapshot = MathHost().classify(NotebookFrontend().lower((document,)))
        [display] = snapshot.display_math
        [artifact] = [fact for fact in snapshot.generated_formulas if fact.kind == "spaced-token"]
        assert artifact.source_math_fact_id == display.fact_id
        assert artifact.text == r"\ f r a c"
        assert artifact.span is not None
        assert artifact.span.cell == 0
        assert artifact.span.cell_line == 2
        assert len(artifact.span.segments) == len(artifact.text)
        raw_segments = [
            document.text[start:end]
            for segment in artifact.span.segments
            for start, end in segment.ranges
        ]
        assert raw_segments == [r"\\", " ", "f", " ", "r", " ", "a", " ", "c"]
        assert artifact.span.end - artifact.span.start > sum(map(len, raw_segments))
        formula_ids.append(artifact.fact_id)

    assert formula_ids[0] == formula_ids[1]

    code_document = notebook(
        notebook_payload(
            code_cell(metadata={}, source=source),
        ),
        path="generated-code.ipynb",
    )
    assert NotebookFrontend().lower((code_document,)).generated_formulas == ()


def test_notebook_frontend_rejects_parsed_input_from_another_document() -> None:
    first = notebook(
        notebook_payload({"cell_type": "markdown", "metadata": {}, "source": "$x$"}),
        path="first.ipynb",
    )
    second = notebook(
        notebook_payload({"cell_type": "markdown", "metadata": {}, "source": "$y$"}),
        path="second.ipynb",
    )

    with pytest.raises(ValueError, match="different SourceDocument"):
        NotebookFrontend().lower(
            (second,),
            parsed={second.path.as_posix(): parse_notebook_input(first)},
        )


def test_notebook_crossrefs_profile_is_accepted_by_config_loader(tmp_path) -> None:
    path = tmp_path / "scieqlint.toml"
    path.write_text('[profile]\nname = "notebook-crossrefs"\n', encoding="utf-8")

    loaded = load_config(path)

    assert loaded.profile.name == "notebook-crossrefs"
    assert loaded.profile.output_profile is None
