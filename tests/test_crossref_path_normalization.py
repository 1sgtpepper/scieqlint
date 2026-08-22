from __future__ import annotations

import json
from dataclasses import replace
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from scieqlint.api import check_documents, graph_documents
from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    ProfileConfig,
    ProjectConfig,
    ScannerConfig,
)
from scieqlint.diag.model import Severity
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.facts.reference import GenericRefFact
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost
from scieqlint.query.reference import ReferenceQueryView


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


@pytest.mark.parametrize("operation", [check_documents, graph_documents])
def test_public_document_apis_reject_paths_with_one_normalized_project_member(operation) -> None:
    first = doc("chapter/../energy.md", "# First\n")
    second = doc("energy.md", "# Second\n")

    with pytest.raises(
        ValueError,
        match=(
            r"^duplicate normalized document path\(s\): energy\.md "
            r"\(chapter/\.\./energy\.md, energy\.md\)$"
        ),
    ):
        operation((first, second), config=Config())


@pytest.mark.parametrize(
    "operation",
    [check_documents, graph_documents],
    ids=["check_documents", "graph_documents"],
)
def test_public_document_apis_reject_normalized_collisions_before_source_kind_validation(
    operation,
) -> None:
    first = SourceDocument.from_text(
        PurePosixPath("chapter/../notes.txt"),
        "# First\n",
        DocumentKind.UNKNOWN,
    )
    second = SourceDocument.from_text(
        PurePosixPath("notes.txt"),
        "# Second\n",
        DocumentKind.UNKNOWN,
    )

    with pytest.raises(
        ValueError,
        match=(
            r"^duplicate normalized document path\(s\): notes\.txt "
            r"\(chapter/\.\./notes\.txt, notes\.txt\)$"
        ),
    ):
        operation((first, second), config=Config())


@pytest.mark.parametrize(
    "operation",
    [check_documents, graph_documents],
    ids=["check_documents", "graph_documents"],
)
def test_public_document_apis_reject_normalized_collisions_when_scanning_disabled(
    operation,
) -> None:
    first = doc("chapter/../energy.md", "# First\n")
    second = doc("energy.md", "# Second\n")
    config = Config(scanner=ScannerConfig(markdown=False))

    with pytest.raises(
        ValueError,
        match=(
            r"^duplicate normalized document path\(s\): energy\.md "
            r"\(chapter/\.\./energy\.md, energy\.md\)$"
        ),
    ):
        operation((first, second), config=config)


@pytest.mark.parametrize(
    "operation",
    [check_documents, graph_documents],
    ids=["check_documents", "graph_documents"],
)
def test_public_document_apis_accept_distinct_normalized_project_members(operation) -> None:
    first = doc("chapter/../energy.md", "# First\n")
    second = doc("chapter/energy.md", "# Second\n")

    result = operation((first, second), config=Config())

    if operation is check_documents:
        assert result.diagnostics == ()
        assert result.math_blocks_checked == 0
    else:
        assert result.nodes == ()
        assert result.edges == ()


def test_workspace_normalizes_project_targets_lexically_without_urls() -> None:
    from scieqlint.io.workspace import normalize_project_path, project_reference_target

    target = project_reference_target(
        PurePosixPath("chapters/index.md"),
        "./section/../energy.md#eq-energy",
    )

    assert target is not None
    assert target.raw_path == "./section/../energy.md"
    assert target.resolved_raw_path == "chapters/./section/../energy.md"
    assert target.normalized_path == PurePosixPath("chapters/energy.md")
    assert target.fragment == "eq-energy"
    assert project_reference_target(PurePosixPath("index.md"), "#eq-energy") is None
    assert project_reference_target(PurePosixPath("index.md"), "https://x/a.md") is None
    assert normalize_project_path("a/../../b.md") == PurePosixPath("../b.md")
    assert normalize_project_path(PureWindowsPath(".")) == PurePosixPath(".")


def test_workspace_handles_malformed_encoded_and_native_destinations() -> None:
    from scieqlint.io.workspace import WorkspaceHost, project_reference_target

    workspace = WorkspaceHost(project_root=PurePosixPath("book"))
    encoded = workspace.project_reference_target(
        PurePosixPath("book/chapters/index.md"),
        "./energy%2Emd?download=1#eq%2Denergy",
    )
    unicode_target = workspace.project_reference_target(
        PurePosixPath("book/index.md"),
        "./caf%C3%A9.md#%C3%A9q",
    )
    windows_relative = workspace.project_reference_target(
        PureWindowsPath("book/chapters/index.md"),
        r"..\energy.md#eq-energy",
    )
    windows = WorkspaceHost(project_root=PureWindowsPath("C:/book")).project_reference_target(
        PureWindowsPath("C:/book/chapters/index.md"),
        r"C:\book\chapters\energy.md#eq-energy",
    )
    unc = WorkspaceHost(
        project_root=PureWindowsPath(r"\\server\share\book")
    ).project_reference_target(
        PureWindowsPath(r"\\server\share\book\index.md"),
        r"\\server\share\book\energy.md#eq-energy",
    )

    assert encoded is not None
    assert encoded.raw_path == "./energy%2Emd"
    assert encoded.normalized_path == PurePosixPath("chapters/energy.md")
    assert encoded.fragment == "eq-energy"
    assert unicode_target is not None
    assert unicode_target.normalized_path == PurePosixPath("café.md")
    assert unicode_target.fragment == "éq"
    assert windows_relative is not None
    assert windows_relative.raw_path == r"..\energy.md"
    assert windows_relative.resolved_raw_path == r"book/chapters/..\energy.md"
    assert windows_relative.normalized_path == PurePosixPath("energy.md")
    assert windows is not None
    assert windows.raw_path == r"C:\book\chapters\energy.md"
    assert windows.resolved_raw_path == r"C:\book\chapters\energy.md"
    assert windows.normalized_path == PurePosixPath("chapters/energy.md")
    assert windows.fragment == "eq-energy"
    assert unc is not None
    assert unc.raw_path == r"\\server\share\book\energy.md"
    assert unc.normalized_path == PurePosixPath("energy.md")
    assert project_reference_target(PurePosixPath("index.md"), "//[x]/#target") is None
    assert (
        project_reference_target(PurePosixPath("index.md"), "%2F%2Fserver/energy.md#target") is None
    )
    assert project_reference_target(PurePosixPath("index.md"), "bad%FF.md#target") is None


def test_workspace_applies_configured_root_to_root_relative_targets() -> None:
    from scieqlint.io.workspace import WorkspaceHost

    workspace = WorkspaceHost(project_root=PurePosixPath("book"))

    target = workspace.project_reference_target(
        PurePosixPath("book/index.md"),
        "/chapters/energy.md#eq-energy",
    )
    escaped = workspace.project_reference_target(
        PurePosixPath("book/index.md"),
        "/../outside.md",
    )

    assert target is not None
    assert target.resolved_raw_path == "book/chapters/energy.md"
    assert target.normalized_path == PurePosixPath("chapters/energy.md")
    assert escaped is None
    assert (
        workspace.project_reference_target(
            PurePosixPath("book/index.md"),
            "/%2E%2E/outside.md#target",
        )
        is None
    )


def test_workspace_normalizes_windows_root_relative_case_and_encoded_paths() -> None:
    from scieqlint.io.workspace import WorkspaceHost

    workspace = WorkspaceHost(project_root=PureWindowsPath("c:/Book"))
    source = PureWindowsPath("C:/book/chapters/index.md")
    root_relative = workspace.project_reference_target(source, r"\CHAPTERS\energy.md#x")
    encoded_root_relative = workspace.project_reference_target(
        source,
        r"%5CCHAPTERS%5Cenergy.md#x",
    )
    encoded_native = workspace.project_reference_target(
        source,
        r"C:%5CBOOK%5Cchapters%5Cenergy.md#x",
    )
    unc_workspace = WorkspaceHost(project_root=PureWindowsPath(r"\\SERVER\SHARE\Book"))
    unc = unc_workspace.project_reference_target(
        PureWindowsPath(r"\\server\share\book\index.md"),
        r"\\server\share\BOOK\energy.md#x",
    )

    assert root_relative is not None
    assert root_relative.normalized_path == PurePosixPath("chapters/energy.md")
    assert encoded_root_relative is not None
    assert encoded_root_relative.normalized_path == PurePosixPath("chapters/energy.md")
    assert encoded_native is not None
    assert encoded_native.normalized_path == PurePosixPath("chapters/energy.md")
    assert unc is not None
    assert unc.normalized_path == PurePosixPath("energy.md")
    assert workspace.normalize_project_path(PureWindowsPath("C:/BOOK/energy.md")) == PurePosixPath(
        "energy.md"
    )


@pytest.mark.parametrize(
    "operation",
    [check_documents, graph_documents],
    ids=["check_documents", "graph_documents"],
)
def test_public_document_apis_ignore_malformed_url_without_disabling_active_link(operation) -> None:
    source = doc(
        "index.md",
        "See [malformed](//[x]/#target).\nSee [active](#missing-active).\n",
    )

    try:
        result = operation((source,), config=Config())
    except ValueError as exc:
        pytest.fail(f"malformed URL destination must not abort analysis: {exc}")

    if operation is check_documents:
        assert result.files_checked == 1
        assert result.math_blocks_checked == 0
        assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]
        diagnostic = result.diagnostics[0]
        assert diagnostic.message == "equation reference target not found: missing-active"
        assert diagnostic.span is not None
        assert diagnostic.span.path == PurePosixPath("index.md")
        assert source.text[diagnostic.span.start : diagnostic.span.end] == "missing-active"
    else:
        assert [node.label for node in result.nodes] == ["missing-active"]
        assert [(edge.target, edge.target_label) for edge in result.edges] == [
            ("label:missing-active", "missing-active")
        ]


@pytest.mark.parametrize(
    "operation",
    [check_documents, graph_documents],
    ids=["check_documents", "graph_documents"],
)
@pytest.mark.parametrize(
    "destination",
    [
        "energy.md#%23",
        "energy.md#%20",
        "energy.md#%C2%A0",
        "#%23",
        "#%20",
        "#%C2%A0",
    ],
)
def test_public_document_apis_ignore_empty_decoded_fragments(
    operation,
    destination: str,
) -> None:
    source = doc(
        "index.md",
        f"See [malformed]({destination}).\nSee [active](#missing-active).\n",
    )

    try:
        result = operation((source,), config=Config())
    except ValueError as exc:
        pytest.fail(f"empty decoded fragment must not abort analysis: {exc}")

    if operation is check_documents:
        assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]
        diagnostic = result.diagnostics[0]
        assert diagnostic.span is not None
        assert source.text[diagnostic.span.start : diagnostic.span.end] == "missing-active"
    else:
        assert [node.label for node in result.nodes] == ["missing-active"]
        assert [(edge.target, edge.target_label) for edge in result.edges] == [
            ("label:missing-active", "missing-active")
        ]


@pytest.mark.parametrize(
    "operation",
    [check_documents, graph_documents],
    ids=["check_documents", "graph_documents"],
)
@pytest.mark.public_regression
def test_public_document_apis_decode_percent_encoded_fragment_only_links(operation) -> None:
    source = doc(
        "index.md",
        "$$\nx = 1\n$$ {#éq}\n\nSee [energy](#%C3%A9q).\n",
    )

    result = operation((source,), config=Config())

    if operation is check_documents:
        assert not [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "REF002"]
    else:
        assert [(edge.target_label, edge.kind) for edge in result.edges] == [("éq", "references")]


@pytest.mark.parametrize(
    "operation",
    [
        check_documents,
        pytest.param(graph_documents, marks=pytest.mark.public_regression),
    ],
    ids=["check_documents", "graph_documents"],
)
@pytest.mark.parametrize("target_kind", ["latex", "notebook"])
@pytest.mark.parametrize("link_prefix", ["/", "./"])
def test_configured_root_cross_format_targets_have_one_check_and_graph_identity(
    operation,
    target_kind: str,
    link_prefix: str,
) -> None:
    extension = "tex" if target_kind == "latex" else "ipynb"
    target_path = PurePosixPath(f"book/chapters/energy.{extension}")
    if target_kind == "latex":
        target = SourceDocument.from_text(
            target_path,
            "\\begin{equation}\nE=mc^2 \\label{eq-energy}\n\\end{equation}\n",
            DocumentKind.LATEX,
        )
    else:
        target = SourceDocument.from_text(
            target_path,
            json.dumps(
                {
                    "cells": [
                        {
                            "cell_type": "markdown",
                            "metadata": {},
                            "source": "$$\nE=mc^2\n$$ {#eq-energy}\n",
                        }
                    ],
                    "metadata": {},
                    "nbformat": 4,
                    "nbformat_minor": 5,
                }
            ),
            DocumentKind.NOTEBOOK,
        )
    source = doc(
        "book/index.md",
        f"See [energy]({link_prefix}chapters/energy.{extension}#eq-energy).\n",
    )
    config = Config(
        project=ProjectConfig(root=PurePosixPath("book")),
        profile=ProfileConfig(name="cross-format-references", output_profile="commonmark"),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )

    result = operation((source, target), config=config)

    if operation is check_documents:
        assert not [
            diagnostic
            for diagnostic in result.diagnostics
            if diagnostic.code in {"REF002", "REF004"}
        ]
    else:
        assert [(edge.target_label, edge.kind) for edge in result.edges] == [
            ("eq-energy", "references")
        ]


def test_frontend_preserves_raw_and_normalized_cross_document_target() -> None:
    source = doc("chapters/index.md", "See [energy](./energy.md#eq-energy).\n")

    snapshot = MySTFrontend().lower((source,))

    assert len(snapshot.generic_refs) == 1
    ref = snapshot.generic_refs[0]
    assert ref.raw_target_path == "./energy.md"
    assert ref.resolved_raw_target_path == "chapters/./energy.md"
    assert ref.normalized_target_path == PurePosixPath("chapters/energy.md")
    assert ref.target_fragment == "eq-energy"
    assert ref.target_span is not None
    assert source.text[ref.target_span.start : ref.target_span.end] == "./energy.md#eq-energy"


def test_generic_reference_identity_normalizes_prefixed_fragment() -> None:
    from scieqlint.facts.reference import generic_reference_identity

    reference = GenericRefFact(
        fact_id="reference",
        document_id="chapters/index.md",
        span=None,
        role_kind="markdown-link",
        target="#eq-energy",
        normalized_target="eq-energy",
        normalized_target_path=PurePosixPath("chapters/energy.md"),
        target_fragment="#eq-energy",
    )

    assert generic_reference_identity(reference) == (
        PurePosixPath("chapters/energy.md"),
        "eq-energy",
    )
    assert (
        generic_reference_identity(
            replace(
                reference,
                role_kind="unsupported",
                normalized_target_path=None,
                target_fragment=None,
            )
        )
        is None
    )


def test_reference_engine_ignores_unsupported_path_roles_after_query_classification() -> None:
    source = doc(
        "index.md",
        "[missing](target.md#missing) [ambiguous](target.md#shared)\n",
    )
    target = doc(
        "target.md",
        "(shared)=\n# First\n\n(shared)=\n# Second\n",
    )
    snapshot = MySTFrontend().lower((source, target))
    snapshot = replace(
        snapshot,
        generic_refs=tuple(replace(ref, role_kind="unsupported") for ref in snapshot.generic_refs),
        project_members=(),
    )
    query = QueryHost(snapshot)

    assert (PurePosixPath("target.md"), "shared") in query.references.target_identity_index()
    assert [ref.target_fragment for ref in query.references.unresolved_generic_refs()] == [
        "missing"
    ]
    assert [ref.target_fragment for ref in query.references.ambiguous_generic_refs()] == ["shared"]
    assert ReferenceEngine().run(query) == ()


def test_frontend_snapshot_preserves_configured_project_member_identity() -> None:
    from scieqlint.io.workspace import WorkspaceHost

    source = doc("book/source.md", "See [target](target.md#target).\n")
    target = doc("book/target.md", "(target)=\n# Target\n")
    snapshot = MySTFrontend(workspace=WorkspaceHost(project_root=PurePosixPath("book"))).lower(
        (source, target)
    )
    references = ReferenceQueryView(snapshot)

    assert tuple(member.normalized_path for member in snapshot.project_members) == (
        PurePosixPath("source.md"),
        PurePosixPath("target.md"),
    )
    assert references.unresolved_generic_refs() == ()
    assert (PurePosixPath("target.md"), "target") in references.target_identity_index()


def test_normalized_only_resolution_emits_exact_reference_diagnostic() -> None:
    source = doc("chapters/index.md", "See [energy](./energy.md#eq-energy).\n")
    target = doc("chapters/energy.md", "(eq-energy)=\n# Energy\n")

    result = check_documents((source, target), config=Config())
    diagnostics = tuple(d for d in result.diagnostics if d.code == "REF006")

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.severity is Severity.WARNING
    assert diagnostic.message.endswith("chapters/./energy.md")
    assert diagnostic.span is not None
    assert diagnostic.span.path == PurePosixPath("chapters/index.md")
    assert (diagnostic.span.line, diagnostic.span.col) == (1, 14)
    assert source.text[diagnostic.span.start : diagnostic.span.end] == "./energy.md#eq-energy"
    assert diagnostic.properties == (
        ("target", "chapters/energy.md#eq-energy"),
        ("raw_path", "chapters/./energy.md"),
        ("normalized_path", "chapters/energy.md"),
        ("raw_match_count", "0"),
        ("normalized_match_count", "1"),
    )


def test_path_normalization_mismatch_indexes_targets_once_for_all_references(monkeypatch) -> None:
    source = doc(
        "chapters/index.md",
        "[first](./energy.md#eq-energy) [second](./energy.md#eq-energy) "
        "[third](./energy.md#eq-energy)\n",
    )
    target = doc("chapters/energy.md", "(eq-energy)=\n# Energy\n")
    snapshot = MySTFrontend().lower((source, target))

    class CountingTargets(tuple):
        iterations = 0

        def __iter__(self):
            type(self).iterations += 1
            return super().__iter__()

    counted_targets = CountingTargets(ReferenceQueryView(snapshot)._target_facts())

    def target_facts(_view: ReferenceQueryView) -> tuple:
        return counted_targets

    monkeypatch.setattr(ReferenceQueryView, "_target_facts", target_facts)

    mismatches = ReferenceQueryView(snapshot).path_normalization_mismatches()

    assert len(mismatches) == 3
    assert CountingTargets.iterations == 2


def test_path_and_fragment_identity_selects_the_referenced_member() -> None:
    source = doc(
        "index.md",
        "[missing](chapter-a.md#shared) [present](chapter-b.md#shared)\n",
    )
    first = doc("chapter-a.md", "(other)=\n# Other\n")
    second = doc("chapter-b.md", "(shared)=\n# Shared\n")

    result = check_documents((source, first, second), config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF004"]
    assert result.diagnostics[0].span is not None
    assert result.diagnostics[0].span.path == PurePosixPath("index.md")


def test_path_and_fragment_identity_prevents_cross_document_ambiguity() -> None:
    source = doc(
        "index.md",
        "[first](chapter-a.md#shared) [second](chapter-b.md#shared)\n",
    )
    first = doc("chapter-a.md", "(shared)=\n# First\n")
    second = doc("chapter-b.md", "(shared)=\n# Second\n")

    result = check_documents((source, first, second), config=Config())

    assert not [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "REF005"]
    assert not [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "REF001"]


def test_fragment_only_reference_stays_in_source_member() -> None:
    source = doc("source.md", "See [local](#shared).\n")
    other = doc("other.md", "(shared)=\n# Shared in another member\n")

    result = check_documents((source, other), config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]


def test_fragment_only_reference_selects_source_member_when_labels_repeat() -> None:
    source = doc("source.md", "(shared)=\n# Source\n\nSee [local](#shared).\n")
    other = doc("other.md", "(shared)=\n# Other\n")

    result = check_documents((source, other), config=Config())

    assert not [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "REF005"]
    assert not [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "REF001"]


def test_duplicate_targets_in_one_member_make_markdown_link_ambiguous() -> None:
    source = doc(
        "source.md",
        "(shared)=\n# First\n\n(shared)=\n# Second\n\nSee [shared](#shared).\n",
    )

    result = check_documents((source,), config=Config())

    assert [
        diagnostic.code for diagnostic in result.diagnostics if diagnostic.code == "REF005"
    ] == ["REF005"]


def test_path_bearing_missing_markdown_target_has_one_query_owner() -> None:
    source = doc(
        "index.md",
        "[missing](chapter.md#missing) [external](https://example.test/chapter.md#missing)\n",
    )

    result = check_documents((source,), config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF004"]
    assert result.diagnostics[0].message.endswith("missing")


def test_duplicate_equation_labels_use_global_namespace() -> None:
    first = doc(
        "a.md",
        "$$\nx = 1\n$$ {#shared}\n\n$$\ny = 1\n$$ {#shared}\n",
    )
    second = doc("b.md", "$$\nz = 1\n$$ {#shared}\n")

    result = check_documents((first, second), config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics].count("REF001") == 2


def test_configured_project_root_resolves_public_root_relative_links() -> None:
    source = doc("book/index.md", "See [energy](/chapters/energy.md#eq-energy).\n")
    target = doc("book/chapters/energy.md", "(eq-energy)=\n$$\nE=mc^2\n$$\n")
    config = Config(project=ProjectConfig(root=PurePosixPath("book")))

    result = check_documents((source, target), config=config)

    assert not [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "REF006"]


def test_already_normalized_and_external_targets_do_not_warn() -> None:
    source = doc(
        "chapters/index.md",
        "[local](energy.md#eq-energy) [external](https://example.test/energy.md)\n",
    )
    target = doc("chapters/energy.md", "(eq-energy)=\n$$E=mc^2$$\n")

    result = check_documents((source, target), config=Config())

    assert not [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "REF006"]
