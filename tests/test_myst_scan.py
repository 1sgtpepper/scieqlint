from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.config.model import Config, ScannerConfig
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import LabelSource, MathContainer, ReferenceSource
from scieqlint.scan.markdown import MarkdownScanner


def test_scans_myst_math_directive_label_and_eq_role() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "```{math}\n:label: energy\nE = m c^2\n```\n\nSee {eq}`energy`.\n",
        DocumentKind.MARKDOWN,
    )
    result = MarkdownScanner().scan(document, Config())
    assert result.blocks[0].container is MathContainer.MARKDOWN_FENCE
    assert [(label.label, label.source) for label in result.labels] == [
        ("energy", LabelSource.MYST_DIRECTIVE_LABEL)
    ]
    assert [(ref.target, ref.source) for ref in result.references] == [
        ("energy", ReferenceSource.MYST_EQ_ROLE)
    ]


def test_math_fence_scanning_can_be_disabled() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "```{math}\n:label: energy\nE = m c^2\n```\n",
        DocumentKind.MARKDOWN,
    )
    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(math_fences=False)),
    )
    assert result.blocks == ()
    assert result.labels == ()


def test_unterminated_math_fence_emits_scan_warning() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "```{math}\na = a\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]
    assert result.diagnostics[0].span.line == 1
    assert result.diagnostics[0].rule == "scanner"
