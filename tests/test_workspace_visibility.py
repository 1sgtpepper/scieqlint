from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

import pytest

from scieqlint.api import check_documents, check_paths, graph_documents
from scieqlint.app import _profile_snapshot
from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    ProfileConfig,
    ProjectConfig,
)
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost


def document() -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("source.md"),
        "{eq}`eq-one`\n",
        DocumentKind.MARKDOWN,
    )


def target_document() -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("target.md"),
        "$$\nx = 1\n$$ {#eq-one}\n",
        DocumentKind.MARKDOWN,
    )


def test_public_visibility_projection_keeps_visible_and_nonvisible_targets_distinct() -> None:
    source = document()
    target = target_document()

    visible = check_documents((source, target), config=Config())
    hidden = check_documents(
        (source, target),
        config=Config(project=ProjectConfig(visibility=(("target.md", "hidden"),))),
    )
    excluded = check_documents(
        (source, target),
        config=Config(project=ProjectConfig(visibility=(("target.md", "excluded"),))),
    )

    assert not any(item.code == "REF008" for item in visible.diagnostics)
    assert [item.code for item in hidden.diagnostics].count("REF008") == 1
    assert [item.code for item in excluded.diagnostics].count("REF008") == 1


def test_public_excluded_visibility_removes_the_document_from_the_graph() -> None:
    source = document()
    target = target_document()

    visible = graph_documents((source, target), config=Config())
    excluded = graph_documents(
        (source, target),
        config=Config(
            project=ProjectConfig(
                visibility=(
                    ("source.md", "excluded"),
                    ("target.md", "excluded"),
                )
            )
        ),
    )

    assert visible.nodes
    assert visible.edges
    assert excluded.nodes == ()
    assert excluded.edges == ()


def test_public_visibility_hides_reference_uses_without_hiding_visible_targets() -> None:
    source = SourceDocument.from_text(
        PurePosixPath("source.md"),
        "{eq}`eq-target`\n",
        DocumentKind.MARKDOWN,
    )
    target = SourceDocument.from_text(
        PurePosixPath("target.md"),
        "$$\nx = 1\n$$ {#eq-target}\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents(
        (source, target),
        config=Config(project=ProjectConfig(visibility=(("source.md", "hidden"),))),
    )

    assert not any(item.code.startswith("REF") for item in result.diagnostics)


def test_hidden_source_missing_reference_is_not_observed_by_either_reference_path() -> None:
    source = SourceDocument.from_text(
        PurePosixPath("source.md"),
        "See {eq}`missing-equation` and {ref}`missing-target`.\n",
        DocumentKind.MARKDOWN,
    )
    active_control = SourceDocument.from_text(
        PurePosixPath("visible.md"),
        source.text,
        DocumentKind.MARKDOWN,
    )

    result = check_documents(
        (source, active_control),
        config=Config(project=ProjectConfig(visibility=(("source.md", "hidden"),))),
    )

    assert [
        (item.code, item.span.path.as_posix() if item.span else None)
        for item in result.diagnostics
        if item.code.startswith("REF")
    ] == [("REF002", "visible.md"), ("REF004", "visible.md")]


@pytest.mark.parametrize("visibility", ["hidden", "excluded"])
def test_nonvisible_code_cell_target_is_not_resolvable_from_visible_reference(
    visibility: Literal["hidden", "excluded"],
) -> None:
    source = SourceDocument.from_text(
        PurePosixPath("source.md"),
        "See {ref}`hidden-cell`.\n",
        DocumentKind.MARKDOWN,
    )
    target = SourceDocument.from_text(
        PurePosixPath("target.md"),
        "```{code-cell} python\n:label: hidden-cell\npass\n```\n",
        DocumentKind.MARKDOWN,
    )

    config = Config(project=ProjectConfig(visibility=(("target.md", visibility),)))
    snapshot = _profile_snapshot((source, target), config)
    query = QueryHost(snapshot)
    [cell] = query.references.code_cell_targets()

    if visibility == "hidden":
        assert query.references.hidden_code_cell_targets() == (cell,)
    else:
        assert query.references.excluded_code_cell_targets() == (cell,)
    assert "hidden-cell" not in query.references.target_index()

    result = check_documents((source, target), config=config)

    assert [item.code for item in result.diagnostics if item.code.startswith("REF")] == ["REF004"]


def test_hidden_target_does_not_supply_reference_display_metadata() -> None:
    source = SourceDocument.from_text(
        PurePosixPath("source.md"),
        "See [](#eq-hidden).\n",
        DocumentKind.MARKDOWN,
    )
    target = SourceDocument.from_text(
        PurePosixPath("target.md"),
        "$$\nx = 1\n$$ {#eq-hidden}\n",
        DocumentKind.MARKDOWN,
    )
    config = Config(
        profile=ProfileConfig(name="reference-display"),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
        project=ProjectConfig(visibility=(("target.md", "hidden"),)),
    )

    snapshot = _profile_snapshot((source, target), config)

    [display] = snapshot.reference_display_text
    assert display.target_fact_ids == ()


def test_unknown_project_visibility_member_is_rejected_at_config_owner() -> None:
    with pytest.raises(ValueError, match="unknown project visibility member"):
        check_documents(
            (document(),),
            config=Config(project=ProjectConfig(visibility=(("typo.md", "hidden"),))),
        )


def test_path_api_reads_project_visibility_from_normal_config(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "source.md").write_text("{eq}`eq-one`\n", encoding="utf-8")
    (tmp_path / "target.md").write_text("$$\nx = 1\n$$ {#eq-one}\n", encoding="utf-8")
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        '[project.visibility]\n"target.md" = "hidden"\n',
        encoding="utf-8",
    )

    result = check_paths(("source.md", "target.md"), config_path=config_path)

    assert [item.code for item in result.diagnostics if item.code == "REF008"] == ["REF008"]


def test_visibility_keys_remain_project_relative_under_configured_root(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "book"
    project.mkdir()
    (project / "source.md").write_text("{eq}`eq-one`\n", encoding="utf-8")
    (project / "target.md").write_text("$$\nx = 1\n$$ {#eq-one}\n", encoding="utf-8")
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        '[project]\nroot = "book"\n\n[project.visibility]\n"target.md" = "hidden"\n',
        encoding="utf-8",
    )

    result = check_paths((), config_path=config_path)

    assert [item.code for item in result.diagnostics if item.code == "REF008"] == ["REF008"]
