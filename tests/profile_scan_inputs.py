"""Build explicit LaTeX scan products for profile-composer tests."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

from scieqlint.config.model import Config
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import EquationLabel, EquationReference, MathBlock
from scieqlint.scan.latex import LatexScanner


class ProfileScanInputs(TypedDict):
    source_blocks: tuple[MathBlock, ...]
    source_labels: tuple[EquationLabel, ...]
    source_references: tuple[EquationReference, ...]


def profile_scan_inputs(documents: Sequence[SourceDocument]) -> ProfileScanInputs:
    latex_documents = tuple(
        document for document in documents if document.kind is DocumentKind.LATEX
    )
    blocks: list[MathBlock] = []
    labels: list[EquationLabel] = []
    references: list[EquationReference] = []
    if latex_documents:
        scanner = LatexScanner()
        config = Config()
        for document in latex_documents:
            scan = scanner.scan(document, config)
            blocks.extend(scan.blocks)
            labels.extend(scan.labels)
            references.extend(scan.references)
    return {
        "source_blocks": tuple(blocks),
        "source_labels": tuple(labels),
        "source_references": tuple(references),
    }
