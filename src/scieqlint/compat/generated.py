"""Small helper to add generated provenance to a ``FactSnapshot``."""

from __future__ import annotations

from scieqlint.facts.generated import GeneratedProvenanceFact
from scieqlint.facts.snapshot import FactSnapshot


def attach_generated_provenance(
    snapshot: FactSnapshot,
    pairs: tuple[tuple[str, str], ...],
) -> FactSnapshot:
    facts = tuple(
        GeneratedProvenanceFact(
            fact_id=f"generated::{source_id}->{generated_id}",
            document_id=generated_id,
            span=None,
            generated_document_id=generated_id,
            source_document_id=source_id,
            tool="configured-pair",
        )
        for source_id, generated_id in pairs
    )
    return FactSnapshot(
        documents=snapshot.documents,
        headings=snapshot.headings,
        sections=snapshot.sections,
        fences=snapshot.fences,
        directives=snapshot.directives,
        code_cells=snapshot.code_cells,
        target_anchors=snapshot.target_anchors,
        generic_refs=snapshot.generic_refs,
        equation_labels=snapshot.equation_labels,
        equation_refs=snapshot.equation_refs,
        inline_math=snapshot.inline_math,
        display_math=snapshot.display_math,
        unknown_math=snapshot.unknown_math,
        project_members=snapshot.project_members,
        hidden_excluded=snapshot.hidden_excluded,
        generated_provenance=(*snapshot.generated_provenance, *facts),
        portability=snapshot.portability,
        metadata=snapshot.metadata,
    )
