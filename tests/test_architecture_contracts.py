from pathlib import PurePosixPath

from scieqlint.compat.architecture_pipeline import analyze_documents_architecture
from scieqlint.io.source import DocumentKind, SourceDocument


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def test_architecture_pipeline_is_deterministic_and_immutable():
    result1 = analyze_documents_architecture((doc("a.md", "# Title\n\nText $x$.\n"),))
    result2 = analyze_documents_architecture((doc("a.md", "# Title\n\nText $x$.\n"),))
    assert result1.summary() == result2.summary()
    assert result1.snapshot.documents[0].path.as_posix() == "a.md"
    assert result1.snapshot.inline_math[0].body == "x"
