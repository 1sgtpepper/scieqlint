"""Equation label and reference checks."""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic
from scieqlint.io.workspace import normalize_project_path
from scieqlint.scan.base import EquationLabel, EquationReference, MathBlock, MathContainer

_DEFAULT_PROJECT_ROOT = PurePosixPath(".")


def check_references(
    labels: tuple[EquationLabel, ...],
    references: tuple[EquationReference, ...],
    *,
    blocks: tuple[MathBlock, ...] = (),
    strict_missing_labels: bool = False,
    project_root: PurePosixPath = _DEFAULT_PROJECT_ROOT,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    labels_by_identity: dict[tuple[PurePosixPath, str], list[EquationLabel]] = defaultdict(list)
    labels_by_name: dict[str, list[EquationLabel]] = defaultdict(list)
    for label in labels:
        label_path = normalize_project_path(label.span.path, project_root=project_root)
        labels_by_identity[(label_path, label.label)].append(label)
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

    for reference in references:
        if reference.normalized_target_path is not None:
            # Path-bearing links are resolved by ReferenceQueryView so the
            # compatibility checker cannot report a second owner diagnostic.
            continue
        reference_path = (
            normalize_project_path(reference.span.path, project_root=project_root)
            if reference.target_fragment is not None
            else None
        )
        if reference_path is not None:
            if (reference_path, reference.target) in labels_by_identity:
                continue
        elif reference.target in labels_by_name:
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
