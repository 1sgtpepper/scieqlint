from pathlib import PurePosixPath

from scieqlint.compat.architecture_pipeline import analyze_documents_architecture
from scieqlint.io.source import DocumentKind, SourceDocument


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def test_generated_output_dropped_anchor_is_error():
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
