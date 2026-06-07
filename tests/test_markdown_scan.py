from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.config.model import Config
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import MathContainer, ReferenceSource
from scieqlint.scan.markdown import MarkdownScanner


def test_scans_display_math_label_and_markdown_reference() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\nE = m c^2\n$$ {#eq-energy}\n\nSee [Eq.](#eq-energy).\n",
        DocumentKind.MARKDOWN,
    )
    result = MarkdownScanner().scan(document, Config())
    assert len(result.blocks) == 1
    assert result.blocks[0].container is MathContainer.MARKDOWN_DISPLAY
    assert result.blocks[0].span.line == 2
    assert [label.label for label in result.labels] == ["eq-energy"]
    assert [(ref.target, ref.source) for ref in result.references] == [
        ("eq-energy", ReferenceSource.MARKDOWN_ANCHOR)
    ]
