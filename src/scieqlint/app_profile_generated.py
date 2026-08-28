"""Generated-profile provenance compatibility at the app boundary."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from scieqlint.config.model import Config
from scieqlint.diag.model import Diagnostic
from scieqlint.facts.generated import (
    GENERATED_PROVENANCE_FACT_SUFFIX,
    GeneratedProvenanceFact,
)
from scieqlint.io.source import SourceDocument
from scieqlint.schema import SchemaHost


def generated_provenance_facts(
    documents: Sequence[SourceDocument],
    config: Config,
) -> tuple[GeneratedProvenanceFact, ...]:
    """Build caller-owned source-to-generated mappings independently of scanning."""

    if config.profile.name != "generated-myst":
        return ()
    return tuple(
        GeneratedProvenanceFact(
            fact_id=f"{document.path.as_posix()}{GENERATED_PROVENANCE_FACT_SUFFIX}",
            document_id=document.path.as_posix(),
            span=None,
            raw=None,
            confidence="generated",
            generated_document_id=document.path.as_posix(),
            source_document_id=document.origin.source_document_id,
            source_kind=(
                document.origin.source_kind
                if document.origin.source_kind is not None
                else config.profile.source_kind
            ),
            conversion_stage=(
                document.origin.conversion_stage
                if document.origin.conversion_stage is not None
                else config.profile.conversion_stage
            ),
            source_sha=document.origin.source_sha,
            tool=document.origin.tool,
            tool_version=document.origin.tool_version,
            preserved_anchor_inventory=document.origin.preserved_anchor_inventory,
        )
        for document in documents
        if document.origin is not None
    )


def project_generated_diagnostic(
    diagnostic: Diagnostic,
    *,
    profile: str,
    generated_provenance_by_id: dict[str, GeneratedProvenanceFact],
    generated_provenance_by_document: dict[str, GeneratedProvenanceFact],
) -> Diagnostic:
    """Attach only caller-owned generated origins to a public diagnostic."""
    provenances: list[GeneratedProvenanceFact] = []
    for fact_id in dict.fromkeys(diagnostic.provenance_ids):
        provenance = generated_provenance_by_id.get(fact_id)
        if provenance is not None:
            provenances.append(provenance)
    if not provenances and diagnostic.span is not None:
        provenance = generated_provenance_by_document.get(diagnostic.span.path.as_posix())
        if provenance is not None:
            provenances.append(provenance)
    if not provenances:
        return diagnostic
    projection = SchemaHost.project_diagnostic(
        diagnostic,
        profile=profile,
        provenances=tuple(provenances),
    )
    return replace(
        diagnostic,
        profile=projection.profile,
        provenance_ids=projection.provenance_ids,
        properties=projection.properties,
    )
