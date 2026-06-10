"""Scanner dispatch for supported source document kinds."""

from __future__ import annotations

from scieqlint.config.model import Config
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import ScanResult
from scieqlint.scan.latex import LatexScanner
from scieqlint.scan.markdown import MarkdownScanner
from scieqlint.scan.notebook import NotebookScanner


def scan_document(document: SourceDocument, config: Config) -> ScanResult:
    """Scan a source document with the scanner that owns its source format."""
    if document.kind is DocumentKind.LATEX:
        return LatexScanner().scan(document, config)
    if document.kind is DocumentKind.NOTEBOOK:
        return NotebookScanner().scan(document, config)
    return MarkdownScanner().scan(document, config)
