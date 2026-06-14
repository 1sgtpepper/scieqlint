from pathlib import PurePosixPath

from scieqlint.compat.architecture_pipeline import analyze_documents_architecture
from scieqlint.engine.generated import GeneratedOutputEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def test_heading_text_preserves_c_sharp_suffix():
    snapshot = MySTFrontend().lower((doc("lecture.md", "# C#\n"),))
    assert snapshot.headings[0].text == "C#"
    assert snapshot.headings[0].slug_candidate == "c"


def test_anchor_with_intervening_paragraph_is_orphaned():
    snapshot = MySTFrontend().lower(
        (doc("lecture.md", "(target)=\nThis paragraph intervenes.\n\n# Heading\n"),)
    )
    assert snapshot.target_anchors[0].placement == "orphaned"


def test_myst_math_directive_label_is_equation_label_fact():
    snapshot = MySTFrontend().lower(
        (
            doc(
                "lecture.md",
                "```{math}\n:label: eq-growth\n\nx_{t+1} = f(x_t)\n```\nSee {eq}`eq-growth`.\n",
            ),
        )
    )
    labels = {label.normalized_label for label in snapshot.equation_labels}
    assert "eq-growth" in labels
    assert snapshot.display_math[0].container == "myst-math-directive"


def test_generated_refs_resolve_across_generated_documents():
    documents = (
        doc("source/a.md", "(shared)=\n# Shared\n"),
        doc("source/b.md", "See {ref}`shared`.\n"),
        doc("generated/a.md", "(shared)=\n# Traducido\n"),
        doc("generated/b.md", "See {ref}`shared`.\n"),
    )
    result = analyze_documents_architecture(
        documents,
        profiles=("scientific-myst", "generated"),
        generated_pairs=(
            ("source/a.md", "generated/a.md"),
            ("source/b.md", "generated/b.md"),
        ),
    )
    assert "GEN003" not in {diagnostic.code for diagnostic in result.diagnostics}


def test_generated_related_locations_are_always_tuple():
    snapshot = MySTFrontend().lower(
        (
            doc("source/a.md", "(lost)=\n# Source\n"),
            doc("generated/a.md", "# Generated\nSee {ref}`lost`.\n"),
        )
    )
    from scieqlint.compat.generated import attach_generated_provenance

    snapshot = attach_generated_provenance(snapshot, (("source/a.md", "generated/a.md"),))
    diagnostics = GeneratedOutputEngine().run(QueryHost(snapshot))
    dropped = [diagnostic for diagnostic in diagnostics if diagnostic.code == "REF014"]
    assert dropped
    assert isinstance(dropped[0].related_locations, tuple)
