"""Equation label and reference checks."""

from __future__ import annotations

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic
from scieqlint.scan.base import EquationLabel, MathBlock, MathContainer


def check_missing_labels(
    blocks: tuple[MathBlock, ...],
    labels: tuple[EquationLabel, ...],
) -> tuple[Diagnostic, ...]:
    """Report unlabeled non-inline blocks for strict reference checking."""
    labeled_blocks = {label.block_id for label in labels if label.block_id is not None}
    info = CATALOG["REF003"]
    return tuple(
        Diagnostic(
            code="REF003",
            severity=info.severity,
            message=info.message,
            span=block.span,
            equation=block.text,
            rule="references",
        )
        for block in blocks
        if block.container is not MathContainer.MARKDOWN_INLINE
        and block.block_id not in labeled_blocks
    )
