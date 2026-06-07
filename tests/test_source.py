from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.io.source import DocumentKind, LineIndex, SourceDocument


def test_line_index_positions() -> None:
    index = LineIndex.from_text("a\nbc\n")
    assert index.position(0) == (1, 1)
    assert index.position(2) == (2, 1)
    assert index.position(4) == (2, 3)


def test_source_document_normalizes_newlines() -> None:
    doc = SourceDocument.from_text(PurePosixPath("README.md"), "a\r\nb", DocumentKind.MARKDOWN)
    assert doc.text == "a\nb"
    assert doc.display_path == "README.md"
