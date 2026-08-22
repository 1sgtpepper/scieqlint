"""Equation label and reference checks."""

from __future__ import annotations

from collections import defaultdict

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic
from scieqlint.scan.base import EquationLabel, EquationReference, MathBlock, MathContainer


def check_references(
    labels: tuple[EquationLabel, ...],
    references: tuple[EquationReference, ...],
    *,
    blocks: tuple[MathBlock, ...] = (),
    strict_missing_labels: bool = False,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    labels_by_name: dict[str, list[EquationLabel]] = defaultdict(list)
    for label in labels:
        labels_by_name[label.label].append(label)

    for same_name in labels_by_name.values():
        if len(same_name) <= 1:
            continue
        for duplicate in same_name[1:]:
            info = CATALOG["REF001"]
            diagnostics.append(
                Diagnostic(
                    code=info.code,
                    severity=info.severity,
                    message=f"{info.message}: {duplicate.label}",
                    span=duplicate.span,
                    rule="references",
                )
            )

    label_names = set(labels_by_name)
    for reference in references:
        if reference.target in label_names:
            continue
        info = CATALOG["REF002"]
        diagnostics.append(
            Diagnostic(
                code=info.code,
                severity=info.severity,
                message=f"{info.message}: {reference.target}",
                span=reference.span,
                detail=f"reference text: {reference.raw}",
                rule="references",
            )
        )

    if strict_missing_labels:
        diagnostics.extend(check_missing_labels(blocks, labels))

    return tuple(
        sorted(diagnostics, key=lambda diagnostic: diagnostic.span.start if diagnostic.span else -1)
    )


def check_missing_labels(
    blocks: tuple[MathBlock, ...],
    labels: tuple[EquationLabel, ...],
) -> tuple[Diagnostic, ...]:
    """Report unlabeled non-inline blocks for strict reference checking."""
    labeled_blocks = {label.block_id for label in labels if label.block_id is not None}
    info = CATALOG["REF003"]
    return tuple(
        Diagnostic(
            code=info.code,
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
