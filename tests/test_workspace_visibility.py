from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

import pytest

from scieqlint.api import check_documents, check_paths, graph_documents
from scieqlint.app import _profile_snapshot
from scieqlint.config.model import Config, ProfileConfig, ProjectConfig, ValidationProfile
from scieqlint.frontend.notebook import NotebookFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.io.workspace import WorkspaceHost
from scieqlint.query.host import QueryHost

HIDDEN_EQUATION_FIXTURE_ROOT = Path("tests/fixtures/project/hidden_equation_references")


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


def notebook_target_document() -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("target.ipynb"),
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": "$$\nx = 1\n$$ {#eq-one}\n",
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        DocumentKind.NOTEBOOK,
    )


def test_notebook_frontend_can_exclude_markdown_cells_without_dropping_identity() -> None:
    notebook = notebook_target_document()

    snapshot = NotebookFrontend().lower((notebook,), _include_markdown=False)

    assert snapshot.documents == (notebook,)
    assert tuple(member.document_id for member in snapshot.project_members) == ("target.ipynb",)
    assert snapshot.display_math == ()
    assert snapshot.equation_labels == ()


def test_markdown_profile_applies_project_members_once() -> None:
    snapshot = _profile_snapshot((document(),), Config())

    assert tuple(member.document_id for member in snapshot.project_members) == ("source.md",)


def test_workspace_visibility_uses_project_root_for_in_memory_documents() -> None:
    target = target_document()
    workspace = WorkspaceHost(project_root=PurePosixPath("book"))

    members, hidden_excluded = workspace.project_facts(
        (target,),
        (("target.md", "hidden"),),
    )

    assert members[0].visibility == "hidden"
    assert tuple(fact.path for fact in hidden_excluded) == (PurePosixPath("target.md"),)


def test_workspace_visibility_uses_windows_case_insensitive_path_identity() -> None:
    target = SourceDocument.from_text(
        PurePosixPath("C:/BOOK/target.md"),
        target_document().text,
        DocumentKind.MARKDOWN,
    )
    workspace = WorkspaceHost(project_root=PureWindowsPath("c:/book"))

    members, hidden_excluded = workspace.project_facts(
        (target,),
        ((r"c:\book\TARGET.md", "hidden"),),
    )

    assert members[0].normalized_path == PurePosixPath("target.md")
    assert members[0].visibility == "hidden"
    assert tuple(fact.path for fact in hidden_excluded) == (target.path,)


@pytest.mark.parametrize(
    ("project_root", "document_paths"),
    [
        (PurePosixPath("book"), ("target.md", "book/target.md")),
        (PurePosixPath("/tmp/book"), ("target.md", "/tmp/book/target.md")),
    ],
    ids=("root-prefixed", "absolute-relative"),
)
def test_workspace_rejects_visibility_identity_aliases(
    project_root: PurePosixPath,
    document_paths: tuple[str, str],
) -> None:
    documents = tuple(
        SourceDocument.from_text(
            PurePosixPath(path),
            target_document().text,
            DocumentKind.MARKDOWN,
        )
        for path in document_paths
    )

    with pytest.raises(ValueError, match="duplicate project visibility document path"):
        WorkspaceHost(project_root=project_root).project_facts(
            documents,
            (("target.md", "hidden"),),
        )


@pytest.mark.parametrize(
    "operation",
    [check_documents, graph_documents],
    ids=("check_documents", "graph_documents"),
)
def test_public_document_apis_reject_visibility_identity_aliases(operation) -> None:
    documents = (
        target_document(),
        SourceDocument.from_text(
            PurePosixPath("book/target.md"),
            target_document().text,
            DocumentKind.MARKDOWN,
        ),
    )
    config = Config(
        project=ProjectConfig(
            root=PurePosixPath("book"),
            visibility=(("target.md", "hidden"),),
        )
    )

    with pytest.raises(ValueError, match="duplicate project visibility document path"):
        operation(documents, config=config)


def test_workspace_visibility_keeps_distinct_identities_assignable() -> None:
    documents = (
        target_document(),
        SourceDocument.from_text(
            PurePosixPath("book/other.md"),
            "# Other\n",
            DocumentKind.MARKDOWN,
        ),
    )

    members, _hidden_excluded = WorkspaceHost(project_root=PurePosixPath("book")).project_facts(
        documents,
        (("target.md", "hidden"),),
    )

    assert tuple((member.document_id, member.visibility) for member in members) == (
        ("target.md", "hidden"),
        ("book/other.md", "visible"),
    )


def test_workspace_visibility_aliases_preserve_general_path_identity_without_config() -> None:
    documents = (
        target_document(),
        SourceDocument.from_text(
            PurePosixPath("book/target.md"),
            target_document().text,
            DocumentKind.MARKDOWN,
        ),
    )

    members, _hidden_excluded = WorkspaceHost(project_root=PurePosixPath("book")).project_facts(
        documents
    )

    assert tuple(member.normalized_path for member in members) == (
        PurePosixPath("../target.md"),
        PurePosixPath("target.md"),
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

    assert [item.code for item in visible.diagnostics] == []
    assert [item.code for item in hidden.diagnostics] == ["REF008"]
    assert [item.code for item in excluded.diagnostics] == ["REF008"]


def test_public_visibility_does_not_change_graph_membership() -> None:
    source = document()
    target = target_document()

    visible = graph_documents((source, target), config=Config())
    excluded = graph_documents(
        (source, target),
        config=Config(
            project=ProjectConfig(visibility=(("source.md", "excluded"), ("target.md", "excluded")))
        ),
    )

    assert visible.nodes
    assert visible.edges
    assert excluded == visible


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


@pytest.mark.parametrize("profile_name", [None, "notebook-crossrefs"])
@pytest.mark.parametrize("visibility", ["hidden", "excluded"])
def test_public_visibility_reports_nonvisible_notebook_equation_targets(
    profile_name: ValidationProfile | None,
    visibility: str,
) -> None:
    result = check_documents(
        (document(), notebook_target_document()),
        config=Config(
            profile=ProfileConfig(name=profile_name),
            project=ProjectConfig(visibility=(("target.ipynb", visibility),)),
        ),
    )

    assert [item.code for item in result.diagnostics] == ["REF008"]


@pytest.mark.parametrize("profile_name", [None, "notebook-crossrefs"])
def test_public_visibility_keeps_visible_notebook_equation_targets_resolvable(
    profile_name: ValidationProfile | None,
) -> None:
    result = check_documents(
        (document(), notebook_target_document()),
        config=Config(profile=ProfileConfig(name=profile_name)),
    )

    assert not any(item.code.startswith("REF") for item in result.diagnostics)


def test_unknown_project_visibility_member_is_rejected_at_config_owner() -> None:
    with pytest.raises(ValueError, match="unknown project visibility member"):
        check_documents(
            (document(),),
            config=Config(project=ProjectConfig(visibility=(("typo.md", "hidden"),))),
        )


def test_workspace_rejects_invalid_visibility_state() -> None:
    with pytest.raises(ValueError, match="unsupported workspace visibility"):
        WorkspaceHost().project_facts((document(),), {"source.md": "private"})


def test_workspace_rejects_conflicting_normalized_visibility_entries() -> None:
    with pytest.raises(ValueError, match="conflicting project visibility entries"):
        WorkspaceHost().project_facts(
            (target_document(),),
            {"target.md": "hidden", "./target.md": "excluded"},
        )


@pytest.mark.parametrize(
    "operation",
    [check_documents, graph_documents],
    ids=("check", "graph"),
)
def test_public_paths_reject_duplicate_visibility_entries_with_different_states(
    operation,
) -> None:
    config = Config(
        project=ProjectConfig(visibility=(("target.md", "hidden"), ("target.md", "excluded")))
    )

    with pytest.raises(ValueError, match="conflicting project visibility entries"):
        operation((target_document(),), config=config)


def test_profile_snapshot_rejects_duplicate_visibility_entries_with_different_states() -> None:
    config = Config(
        project=ProjectConfig(visibility=(("target.md", "hidden"), ("target.md", "excluded")))
    )

    with pytest.raises(ValueError, match="conflicting project visibility entries"):
        _profile_snapshot((target_document(),), config)


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


def test_public_visibility_applies_to_project_relative_fixture_documents() -> None:
    source_text = (HIDDEN_EQUATION_FIXTURE_ROOT / "source.md").read_text(encoding="utf-8")
    hidden_text = (HIDDEN_EQUATION_FIXTURE_ROOT / "hidden.md").read_text(encoding="utf-8")
    source = SourceDocument.from_text(
        PurePosixPath("source.md"),
        source_text,
        DocumentKind.MARKDOWN,
    )
    hidden = SourceDocument.from_text(
        PurePosixPath("hidden.md"),
        hidden_text,
        DocumentKind.MARKDOWN,
    )

    try:
        result = check_documents(
            (source, hidden),
            config=Config(
                project=ProjectConfig(
                    root=PurePosixPath("book"),
                    visibility=(("hidden.md", "hidden"),),
                )
            ),
        )
    except ValueError as exc:
        pytest.fail(f"check_documents rejected project-relative visibility: {exc}")

    assert [item.code for item in result.diagnostics] == ["REF008"]
    diagnostic = result.diagnostics[0]
    assert diagnostic.message == (
        "equation reference matches a hidden or excluded target: eq:shared"
    )
    assert diagnostic.span is not None
    target_start = source_text.index("eq:shared")
    assert diagnostic.span.path == PurePosixPath("source.md")
    assert diagnostic.span.start == target_start
    assert diagnostic.span.end == target_start + len("eq:shared")
    assert (diagnostic.span.line, diagnostic.span.col) == source.line_index.position(target_start)


def test_absolute_path_spelling_keeps_project_visibility_project_relative(
    tmp_path, monkeypatch
) -> None:
    project = tmp_path / "book"
    project.mkdir()
    for name in ("source.md", "hidden.md"):
        (project / name).write_text(
            (HIDDEN_EQUATION_FIXTURE_ROOT / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        '[project]\nroot = "book"\n\n[project.visibility]\n"hidden.md" = "hidden"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = check_paths((), config_path=config_path, absolute_paths=True)

    assert [item.code for item in result.diagnostics] == ["REF008"]
    diagnostic = result.diagnostics[0]
    assert diagnostic.span is not None
    assert diagnostic.span.path == PurePosixPath((project / "source.md").as_posix())


def test_absolute_documents_keep_graph_edges_and_diagnostics_project_relative(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "book"
    source_path = PurePosixPath((project / "source.md").as_posix())
    target_path = PurePosixPath((project / "target.md").as_posix())
    source_text = "[shared](target.md#eq:shared)\n"
    target_text = "$$\nx = 1\n$$ {#eq:shared}\n"
    source = SourceDocument.from_text(source_path, source_text, DocumentKind.MARKDOWN)
    target = SourceDocument.from_text(target_path, target_text, DocumentKind.MARKDOWN)
    config = Config(project=ProjectConfig(root=PurePosixPath("book")))

    result = check_documents((source, target), config=config)
    graph = graph_documents((source, target), config=config)

    assert result.files_checked == 2
    assert result.math_blocks_checked == 1
    assert result.diagnostics == ()
    assert result.exit_code() == 0
    assert graph.schema_version == "0.3"
    assert [
        (
            node.id,
            node.kind,
            node.label,
            node.source,
            node.span.path,
            node.span.line,
            node.span.col,
            node.span.end_line,
            node.span.end_col,
            node.span.cell,
            node.span.cell_line,
        )
        for node in graph.nodes
    ] == [
        (
            f"ref:{source_path}:9",
            "reference",
            "eq:shared",
            "markdown_anchor",
            source_path,
            1,
            10,
            1,
            28,
            None,
            None,
        ),
        (
            f"eq:{target_path}:14",
            "equation",
            "eq:shared",
            "markdown_anchor",
            target_path,
            3,
            6,
            3,
            14,
            None,
            None,
        ),
    ]
    assert [
        (edge.source, edge.target, edge.kind, edge.target_label, edge.raw, edge.source_kind)
        for edge in graph.edges
    ] == [
        (
            f"ref:{source_path}:9",
            f"eq:{target_path}:14",
            "references",
            "eq:shared",
            "[shared](target.md#eq:shared)",
            "markdown_anchor",
        )
    ]


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
