"""Equation label and reference checks."""

from __future__ import annotations

from collections import defaultdict

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic
from scieqlint.scan.base import EquationLabel, EquationReference, MathBlock


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
        labeled_blocks = {label.block_id for label in labels if label.block_id is not None}
        for block in blocks:
            if block.block_id in labeled_blocks:
                continue
            info = CATALOG["REF003"]
            diagnostics.append(
                Diagnostic(
                    code=info.code,
                    severity=info.severity,
                    message=info.message,
                    span=block.span,
                    equation=block.text,
                    rule="references",
                )
            )

    return tuple(
        sorted(diagnostics, key=lambda diagnostic: diagnostic.span.start if diagnostic.span else -1)
    )
