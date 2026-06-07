from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.api import check_documents
from scieqlint.config.model import AlgebraConfig, ChecksConfig, Config, ReferencesConfig
from scieqlint.io.source import DocumentKind, SourceDocument


def test_check_documents_runs_scanner_and_checks() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        DocumentKind.MARKDOWN,
    )
    result = check_documents([document], config=Config())
    assert result.files_checked == 1
    assert result.math_blocks_checked == 1
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["ALG001"]


def test_check_documents_honors_disabled_algebra_check() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        DocumentKind.MARKDOWN,
    )
    config = Config(checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)))
    result = check_documents([document], config=config)
    assert result.diagnostics == ()


def test_check_documents_honors_strict_missing_label_config() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\na = a\n$$\n",
        DocumentKind.MARKDOWN,
    )
    config = Config(checks=ChecksConfig(references=ReferencesConfig(missing_label_strict=True)))
    result = check_documents([document], config=config)
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF003"]
