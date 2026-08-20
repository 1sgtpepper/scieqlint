"""Source-specific lowering into source-neutral cross-reference metadata facts."""

from __future__ import annotations

from collections.abc import Sequence

from scieqlint.facts.reference import (
    CrossrefMetadataFact,
    EquationLabelFact,
    TargetAnchorFact,
)
from scieqlint.facts.structure import CodeCellFact
from scieqlint.io.source import SourceDocument

from .myst_shared import crossref_target_kind

_CROSSREF_DISPLAY_KEYS = frozenset({"cap", "caption", "fig-cap", "lst-cap", "tbl-cap"})


def crossref_metadata_facts(
    document: SourceDocument,
    target_anchors: Sequence[TargetAnchorFact] = (),
    equation_labels: Sequence[EquationLabelFact] = (),
    code_cells: Sequence[CodeCellFact] = (),
) -> tuple[CrossrefMetadataFact, ...]:
    """Lower source-owned target definitions into conflict metadata facts."""

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
                target_kind=anchor.target_kind,
                source_format=source_format,
                output_boundary=boundary,
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
                target_kind="equation",
                source_format=source_format,
                output_boundary=boundary,
                target_metadata=(("label_syntax_kind", label.label_syntax_kind),),
                target_span=target_span,
            )
        )
    for cell in code_cells:
        if cell.label is None:
            continue
        target_kind = crossref_target_kind(cell.label)
        if target_kind is None:
            continue
        options = cell.option_dict()
        facts.append(
            CrossrefMetadataFact(
                fact_id=f"{cell.fact_id}::crossref-metadata",
                document_id=cell.document_id,
                span=cell.span,
                raw=cell.raw,
                source_fact_id=cell.fact_id,
                logical_target=cell.label,
                normalized_target=cell.normalized_label or cell.label,
                target_kind=target_kind,
                source_format=cell.source_format,
                output_boundary=boundary,
                target_metadata=tuple(
                    sorted(
                        (key, value)
                        for key, value in options.items()
                        if key in _CROSSREF_DISPLAY_KEYS
                    )
                ),
                target_span=cell.label_span or cell.span,
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
