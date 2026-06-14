from pathlib import PurePosixPath

from scieqlint.compat.architecture_pipeline import analyze_documents_architecture
from scieqlint.compat.generated import attach_generated_provenance
from scieqlint.engine.generated import GeneratedOutputEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def generated_diagnostics(
    documents: tuple[SourceDocument, ...],
    pairs: tuple[tuple[str, str], ...],
):
    snapshot = MySTFrontend().lower(documents)
    snapshot = attach_generated_provenance(snapshot, pairs)
    return GeneratedOutputEngine().run(QueryHost(snapshot))


def test_generated_output_reports_dropped_anchor_and_unresolved_ref():
    diagnostics = generated_diagnostics(
        (
            doc("source/jax_intro.md", "(jax_at_workaround)=\n#### A Workaround\n"),
            doc("generated/jax_intro.md", "#### 变通方法\n\nSee {ref}`jax_at_workaround`.\n"),
        ),
        (("source/jax_intro.md", "generated/jax_intro.md"),),
    )

    by_code = {diagnostic.code: diagnostic for diagnostic in diagnostics}
    assert by_code["REF014"].severity_default.value == "error"
    assert by_code["REF014"].related_locations
    assert by_code["GEN003"].severity_default.value == "error"


def test_generated_output_accepts_preserved_anchor_inventory():
    diagnostics = generated_diagnostics(
        (
            doc("source/a.md", "(shared)=\n# Shared\n"),
            doc("generated/a.md", "(shared)=\n# Traducido\n\nSee {ref}`shared`.\n"),
        ),
        (("source/a.md", "generated/a.md"),),
    )

    assert {diagnostic.code for diagnostic in diagnostics}.isdisjoint({"REF014", "GEN003"})


def test_architecture_pipeline_surfaces_generated_errors():
    source = doc("source/jax_intro.md", "(jax_at_workaround)=\n#### A Workaround\n")
    generated = doc("generated/jax_intro.md", "#### 变通方法\n\nSee {ref}`jax_at_workaround`.\n")

    result = analyze_documents_architecture(
        (source, generated),
        profiles=("scientific-myst", "generated"),
        generated_pairs=(("source/jax_intro.md", "generated/jax_intro.md"),),
    )

    codes = [diagnostic.code for diagnostic in result.diagnostics]
    assert "REF014" in codes
    assert "GEN003" in codes
    assert any(d.severity.value == "error" for d in result.diagnostics if d.code == "REF014")
