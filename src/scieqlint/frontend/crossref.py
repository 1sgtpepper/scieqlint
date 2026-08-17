"""Source-specific lowering into source-neutral cross-reference metadata facts."""

from __future__ import annotations

from collections.abc import Sequence

from scieqlint.facts.reference import (
    CrossrefMetadataFact,
    EquationRefFact,
    GenericRefFact,
)
from scieqlint.io.source import SourceDocument


def crossref_metadata_facts(
    document: SourceDocument,
    generic_refs: Sequence[GenericRefFact],
    equation_refs: Sequence[EquationRefFact],
) -> tuple[CrossrefMetadataFact, ...]:
    """Lower reference syntax without interpreting cross-output conflicts."""

    facts: list[CrossrefMetadataFact] = []
    source_format = document.kind.value
    boundary = document.path.as_posix()
    for ref in generic_refs:
        metadata = () if ref.title is None else (("display_text", ref.title),)
        facts.append(
            CrossrefMetadataFact(
                fact_id=f"{ref.fact_id}::crossref-metadata",
                document_id=ref.document_id,
                span=ref.span,
                raw=ref.raw,
                source_fact_id=ref.fact_id,
                logical_target=ref.target,
                normalized_target=ref.normalized_target,
                reference_kind=ref.role_kind,
                source_format=source_format,
                output_boundary=boundary,
                display_metadata=metadata,
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
                reference_kind=ref.ref_kind,
                source_format=source_format,
                output_boundary=boundary,
                display_metadata=(("reference_role", ref.ref_kind),),
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
