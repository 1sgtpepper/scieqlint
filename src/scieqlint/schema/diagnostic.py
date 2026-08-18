"""SchemaHost-owned diagnostic metadata projection.

This is the small projection seam needed by generated provenance. The complete
AnalysisResult registry and serializer migration remain owned by #190/#191.
"""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.diag.model import Diagnostic
from scieqlint.facts.generated import GeneratedProvenanceFact

DIAGNOSTIC_PROJECTION_VERSION = "diagnostic-metadata/0.1"


@dataclass(frozen=True, slots=True)
class DiagnosticProjection:
    """Versioned metadata values reporters may serialize."""

    version: str
    profile: str | None
    provenance_ids: tuple[str, ...]
    properties: tuple[tuple[str, str], ...]


class SchemaHost:
    """Own diagnostic metadata projection and generated-origin field naming."""

    _SUPPORTED_PROJECTION_VERSIONS = frozenset({DIAGNOSTIC_PROJECTION_VERSION})

    @classmethod
    def project_diagnostic(
        cls,
        diagnostic: Diagnostic,
        *,
        version: str = DIAGNOSTIC_PROJECTION_VERSION,
    ) -> DiagnosticProjection:
        if version not in cls._SUPPORTED_PROJECTION_VERSIONS:
            raise ValueError(f"unsupported diagnostic projection version: {version}")
        return DiagnosticProjection(
            version=version,
            profile=diagnostic.profile,
            provenance_ids=diagnostic.provenance_ids,
            properties=diagnostic.properties,
        )

    @staticmethod
    def generated_provenance_properties(
        provenance: GeneratedProvenanceFact,
        *,
        prefix: str = "",
    ) -> tuple[tuple[str, str], ...]:
        """Return stable public property names for one generated-origin fact."""

        properties = [(f"{prefix}generated_document", provenance.generated_document_id)]
        if provenance.source_document_id is not None:
            properties.append((f"{prefix}source_document", provenance.source_document_id))
        if provenance.source_kind is not None:
            properties.append((f"{prefix}source_kind", provenance.source_kind))
        if provenance.conversion_stage is not None:
            properties.append((f"{prefix}conversion_stage", provenance.conversion_stage))
        return tuple(properties)
