from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.app import check_documents
from scieqlint.config.model import Config, ProjectConfig
from scieqlint.diag.model import Severity
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.io.workspace import WorkspaceHost, normalize_project_path, project_reference_target
from scieqlint.query.host import QueryHost


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def test_workspace_normalizes_project_targets_lexically_without_urls() -> None:
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


def test_workspace_applies_configured_root_to_root_relative_targets() -> None:
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
    assert escaped is not None
    assert escaped.normalized_path == PurePosixPath("../outside.md")


def test_frontend_preserves_raw_and_normalized_cross_document_target() -> None:
    source = doc("chapters/index.md", "See [energy](./energy.md#eq-energy).\n")

    snapshot = MySTFrontend().lower((source,))

    assert len(snapshot.generic_refs) == 1
    ref = snapshot.generic_refs[0]
    assert ref.target == "eq-energy"
    assert ref.normalized_target == "eq-energy"
    assert ref.raw_target_path == "./energy.md"
    assert ref.resolved_raw_target_path == "chapters/./energy.md"
    assert ref.normalized_target_path == PurePosixPath("chapters/energy.md")
    assert ref.target_fragment == "eq-energy"
    assert ref.target_span is not None
    assert source.text[ref.target_span.start : ref.target_span.end] == "./energy.md#eq-energy"


def test_normalized_only_resolution_emits_exact_reference_diagnostic() -> None:
    source = doc("chapters/index.md", "See [energy](./energy.md#eq-energy).\n")
    target = doc("chapters/energy.md", "(eq-energy)=\n$$\nE=mc^2\n$$\n")

    result = check_documents((source, target), config=Config())
    diagnostics = tuple(result.diagnostics)

    assert [diagnostic.code for diagnostic in diagnostics] == ["REF006"]
    diagnostic = diagnostics[0]
    assert diagnostic.severity is Severity.WARNING
    assert diagnostic.message.endswith("chapters/./energy.md")
    assert diagnostic.span is not None
    assert diagnostic.span.path == PurePosixPath("chapters/index.md")
    assert (diagnostic.span.line, diagnostic.span.col) == (1, 14)
    assert source.text[diagnostic.span.start : diagnostic.span.end] == "./energy.md#eq-energy"
    assert diagnostic.properties == (
        ("raw_path", "chapters/./energy.md"),
        ("normalized_path", "chapters/energy.md"),
        ("raw_match_count", "0"),
        ("normalized_match_count", "1"),
    )


def test_cross_document_resolution_uses_the_referenced_member_for_twins() -> None:
    source = doc(
        "index.md",
        "[wrong](chapter-a.md#shared) [right](chapter-b.md#shared)\n",
    )
    first = doc("chapter-a.md", "(other)=\n```{figure}\nother.png\n```\n")
    second = doc("chapter-b.md", "(shared)=\n```{figure}\nshared.png\n```\n")

    snapshot = MySTFrontend().lower((source, first, second))

    assert [fact.target_type for fact in snapshot.reference_display_text] == [
        None,
        "figure",
    ]
    unresolved = QueryHost(snapshot).references.unresolved_generic_refs()
    assert [ref.normalized_target_path for ref in unresolved] == [PurePosixPath("chapter-a.md")]


def test_cross_document_resolution_reports_unique_and_ambiguous_fragments() -> None:
    source = doc(
        "index.md",
        "[unique](chapter.md#unique) [ambiguous](chapter.md#shared)\n",
    )
    target = doc(
        "chapter.md",
        "(unique)=\n```{figure}\nunique.png\n```\n\n"
        "(shared)=\n```{figure}\nfirst.png\n```\n\n"
        "(shared)=\n```{figure}\nsecond.png\n```\n",
    )

    snapshot = MySTFrontend().lower((source, target))

    assert [fact.target_type for fact in snapshot.reference_display_text] == [
        "figure",
        None,
    ]
    query = QueryHost(snapshot).references
    assert query.unresolved_generic_refs() == ()
    assert [ref.target_fragment for ref in query.ambiguous_generic_refs()] == ["shared"]


def test_cross_document_resolution_reports_missing_member_and_fragment() -> None:
    source = doc(
        "index.md",
        "[member](missing.md#shared) [fragment](chapter.md#missing)\n",
    )
    target = doc("chapter.md", "(other)=\n```{figure}\nother.png\n```\n")
    twin = doc("elsewhere.md", "(shared)=\n```{figure}\nshared.png\n```\n")

    snapshot = MySTFrontend().lower((source, target, twin))

    assert [fact.target_type for fact in snapshot.reference_display_text] == [
        None,
        None,
    ]
    unresolved = QueryHost(snapshot).references.unresolved_generic_refs()
    assert [ref.target_fragment for ref in unresolved] == ["shared", "missing"]


def test_fragment_only_link_cannot_resolve_against_wrong_document_twin() -> None:
    source = doc(
        "index.md",
        "[local](#shared)\n\n(shared)=\n```{figure}\nlocal.png\n```\n",
    )
    twin = doc("other.md", "(shared)=\n```{figure}\nother.png\n```\n")

    snapshot = MySTFrontend().lower((source, twin))
    [ref] = snapshot.generic_refs

    assert ref.normalized_target_path == PurePosixPath("index.md")
    assert [fact.target_type for fact in snapshot.reference_display_text] == ["figure"]
    assert QueryHost(snapshot).references.unresolved_generic_refs() == ()
    assert QueryHost(snapshot).references.ambiguous_generic_refs() == ()


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
