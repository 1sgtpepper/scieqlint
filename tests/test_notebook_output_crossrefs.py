from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

from scieqlint.app import _profile_snapshot, check_documents
from scieqlint.config.load import load_config
from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    ProfileConfig,
    ValidationProfile,
)
from scieqlint.engine.portability import PortabilityEngine
from scieqlint.frontend.notebook import NotebookFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
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


def config(profile: ValidationProfile | None = "notebook-crossrefs") -> Config:
    return Config(
        profile=ProfileConfig(name=profile),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )


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
    assert [output.span.cell_line for output in snapshot.notebook_outputs if output.span] == [
        1,
        1,
    ]
    assert [fact.output_boundary for fact in snapshot.crossref_metadata] == [
        "theme.ipynb::notebook-cell::0::output::0",
        "theme.ipynb::notebook-cell::0::output::1",
    ]
    assert [fact.reference_kind for fact in snapshot.crossref_metadata] == [
        "figure",
        "figure",
    ]
    assert QueryHost(snapshot).references.conflicting_metadata() == ()


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

    result = check_documents((document,), config=config())

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
                    "plot()\n"
                    "#| label: fig-late\n"
                ),
            )
        )
    )

    snapshot = NotebookFrontend().lower((document,))
    [cell] = snapshot.code_cells
    diagnostics = PortabilityEngine(profile="notebook-crossrefs").run(QueryHost(snapshot))

    assert cell.label == "fig-source"
    assert cell.option_dict()["fig-cap"] == "Source caption"
    assert cell.option_dict()["renderings"] == "[light, dark]"
    assert [item.code for item in diagnostics] == ["PORT004"]


def test_renderings_and_crossrefs_are_valid_when_not_combined() -> None:
    document = notebook(
        notebook_payload(
            code_cell(metadata={"renderings": ["light", "dark"]}),
            code_cell(metadata={"label": "fig-static", "fig-cap": "Static"}),
            code_cell(metadata={"label": "theme", "renderings": ["light", "dark"]}),
        )
    )

    result = check_documents((document,), config=config())

    assert [item for item in result.diagnostics if item.code == "PORT004"] == []


def test_caption_only_crossref_option_conflicts_with_renderings() -> None:
    document = notebook(
        notebook_payload(
            code_cell(metadata={"tbl-cap": "Summary", "renderings": ["light", "dark"]})
        )
    )

    snapshot = _profile_snapshot((document,), config())
    conflicts = QueryHost(snapshot).portability.notebook_rendering_conflicts()
    diagnostics = PortabilityEngine(profile="notebook-crossrefs").run(QueryHost(snapshot))

    assert len(conflicts) == 1
    assert conflicts[0].crossref_options == ("tbl-cap",)
    assert [item.code for item in diagnostics] == ["PORT004"]
    assert dict(diagnostics[0].properties)["label"] == "<caption-only cell>"


def test_markdown_executable_cells_use_the_same_policy_surface() -> None:
    document = markdown(
        "```python\n"
        "#| label: fig-theme\n"
        "#| fig-cap: Theme comparison\n"
        "#| renderings: [light, dark]\n"
        "plot()\n"
        "```\n"
    )

    result = check_documents((document,), config=config())

    [diagnostic] = [item for item in result.diagnostics if item.code == "PORT004"]
    assert diagnostic.span is not None
    assert diagnostic.span.cell is None
    assert dict(diagnostic.properties)["source_format"] == "markdown"


def test_profile_is_opt_in_and_malformed_notebook_metadata_is_bounded() -> None:
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
        )
    )

    snapshot = NotebookFrontend().lower((document,))
    default_result = check_documents((document,), config=config(None))

    assert len(snapshot.code_cells) == 2
    assert snapshot.notebook_outputs == ()
    assert snapshot.code_cells[0].raw is None
    assert "renderings" not in snapshot.code_cells[1].option_dict()
    assert [item for item in default_result.diagnostics if item.code == "PORT004"] == []


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


def test_notebook_crossrefs_profile_is_accepted_by_config_loader(tmp_path) -> None:
    path = tmp_path / "scieqlint.toml"
    path.write_text('[profile]\nname = "notebook-crossrefs"\n', encoding="utf-8")

    loaded = load_config(path)

    assert loaded.profile.name == "notebook-crossrefs"
    assert loaded.profile.output_profile is None
