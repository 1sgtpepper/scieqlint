from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.api import check_documents
from scieqlint.config.model import (
    AlgebraConfig,
    BaselineConfig,
    ChecksConfig,
    Config,
    ReferencesConfig,
)
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


def test_check_documents_marks_markdown_next_line_suppression() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<!-- scieqlint-disable-next-line ALG001 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert result.exit_code() == 0
    assert [(diagnostic.code, diagnostic.suppressed) for diagnostic in result.diagnostics] == [
        ("ALG001", True)
    ]


def test_check_documents_warns_for_unknown_suppression_code() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<!-- scieqlint-disable-next-line NOPE999 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert result.exit_code() == 1
    assert [(diagnostic.code, diagnostic.suppressed) for diagnostic in result.diagnostics] == [
        ("SUP001", False),
        ("ALG001", False),
    ]


def test_check_documents_does_not_suppress_different_code() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<!-- scieqlint-disable-next-line REF002 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert result.exit_code() == 1
    assert [(diagnostic.code, diagnostic.suppressed) for diagnostic in result.diagnostics] == [
        ("ALG001", False)
    ]


def test_check_documents_does_not_load_path_baselines() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        DocumentKind.MARKDOWN,
    )
    config = Config(baseline=BaselineConfig(files=("missing-baseline.json",)))

    result = check_documents([document], config=config)

    assert result.exit_code() == 1
    assert result.diagnostics[0].suppressed is False
