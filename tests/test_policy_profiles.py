from pathlib import PurePosixPath

from scieqlint.compat.architecture_pipeline import analyze_documents_architecture
from scieqlint.io.source import DocumentKind, SourceDocument


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath("lecture.md"), text, DocumentKind.MARKDOWN)


def test_strict_ci_remaps_heading_warning_to_error():
    result = analyze_documents_architecture(
        (doc("####Title\n"),),
        profiles=("scientific-myst", "strict-ci"),
    )
    diag = next(d for d in result.diagnostics if d.code == "STR001")
    assert diag.severity.value == "error"


def test_default_profile_does_not_include_heading_style_rule():
    result = analyze_documents_architecture((doc("####Title\n"),), profiles=("default",))
    assert "STR001" not in [d.code for d in result.diagnostics]
