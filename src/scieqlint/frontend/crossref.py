"""Source-specific lowering into source-neutral cross-reference metadata facts."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePosixPath

from scieqlint.facts.reference import (
    CrossrefMetadataFact,
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    TargetAnchorFact,
)
from scieqlint.io.source import SourceDocument
from scieqlint.io.workspace import WorkspaceHost


def crossref_metadata_facts(
    document: SourceDocument,
    generic_refs: Sequence[GenericRefFact],
    equation_refs: Sequence[EquationRefFact],
    *,
    workspace: WorkspaceHost,
    target_anchors: Sequence[TargetAnchorFact] = (),
    equation_labels: Sequence[EquationLabelFact] = (),
) -> tuple[CrossrefMetadataFact, ...]:
    """Lower source references and resolved target definitions."""

    facts: list[CrossrefMetadataFact] = []
    source_format = document.kind.value
    boundary = document.path.as_posix()
    for anchor in target_anchors:
        if anchor.placement == "orphaned" or anchor.target_kind is None:
            continue
        target_span = anchor.label_span or anchor.span
        facts.append(
            CrossrefMetadataFact(
                fact_id=f"{anchor.fact_id}::crossref-metadata",
                document_id=anchor.document_id,
                span=anchor.span,
                raw=anchor.raw,
                source_fact_id=anchor.fact_id,
                logical_target=anchor.label,
                normalized_target=anchor.normalized_label,
                normalized_target_path=workspace.normalize_project_path(document.path),
                source_format=source_format,
                output_boundary=boundary,
                resolved_target_kind=anchor.target_kind,
                metadata_kind="target-definition",
                target_metadata=(("placement", anchor.placement),),
                target_span=target_span,
            )
        )
    for label in equation_labels:
        target_span = label.label_span or label.span
        facts.append(
            CrossrefMetadataFact(
                fact_id=f"{label.fact_id}::crossref-metadata",
                document_id=label.document_id,
                span=label.span,
                raw=label.raw,
                source_fact_id=label.fact_id,
                logical_target=label.label,
                normalized_target=label.normalized_label,
                normalized_target_path=workspace.normalize_project_path(document.path),
                source_format=source_format,
                output_boundary=boundary,
                resolved_target_kind="equation",
                metadata_kind="target-definition",
                target_metadata=(("label_syntax_kind", label.label_syntax_kind),),
                target_span=target_span,
            )
        )
    for ref in generic_refs:
        facts.append(
            CrossrefMetadataFact(
                fact_id=f"{ref.fact_id}::crossref-metadata",
                document_id=ref.document_id,
                span=ref.span,
                raw=ref.raw,
                source_fact_id=ref.fact_id,
                logical_target=ref.target,
                normalized_target=ref.normalized_target,
                normalized_target_path=_reference_target_path(ref, document, workspace),
                source_format=source_format,
                output_boundary=boundary,
                reference_role=ref.role_kind,
                display_title=ref.title,
                metadata_kind="reference-use",
                target_span=ref.target_span,
            )
        )
    for ref in equation_refs:
        facts.append(
            CrossrefMetadataFact(
                fact_id=f"{ref.fact_id}::crossref-metadata",
                document_id=ref.document_id,
                span=ref.span,
                raw=ref.raw,
                source_fact_id=ref.fact_id,
                logical_target=ref.target,
                normalized_target=ref.normalized_target,
                source_format=source_format,
                output_boundary=boundary,
                reference_role=ref.ref_kind,
                display_title=ref.title,
                metadata_kind="reference-use",
                target_span=ref.target_span,
            )
        )
    return tuple(
        sorted(
            facts,
            key=lambda fact: (
                fact.span.start if fact.span is not None else -1,
                fact.fact_id,
            ),
        )
    )


def _reference_target_path(
    ref: GenericRefFact,
    document: SourceDocument,
    workspace: WorkspaceHost,
) -> PurePosixPath | None:
    if ref.target_fragment is None:
        return None
    return ref.normalized_target_path or workspace.normalize_project_path(document.path)
