from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.check.algebra import check_algebra
from scieqlint.config.model import Config
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.markdown import MarkdownScanner


def _first_block(text: str):
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)
    return MarkdownScanner().scan(document, Config()).blocks[0]


def test_false_polynomial_identity_reports_residual() -> None:
    diagnostics = check_algebra(_first_block("$$\n(a+b)^2 = a^2 + b^2\n$$\n"))
    assert [diagnostic.code for diagnostic in diagnostics] == ["ALG001"]
    assert diagnostics[0].detail == "left - right = 2*a*b"


def test_true_polynomial_identity_is_quiet() -> None:
    diagnostics = check_algebra(_first_block("$$\n(a+b)^2 = a^2 + 2*a*b + b^2\n$$\n"))
    assert diagnostics == ()


def test_assignment_with_different_symbols_is_not_treated_as_identity() -> None:
    diagnostics = check_algebra(_first_block("$$\nE = m c^2\n$$\n"))
    assert diagnostics == ()
