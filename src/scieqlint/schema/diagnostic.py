"""SchemaHost-owned diagnostic metadata projection.

This is the small projection seam needed by generated provenance. The complete
AnalysisResult registry and serializer migration remain owned by #190/#191.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from scieqlint.diag.model import Diagnostic

DIAGNOSTIC_PROJECTION_VERSION = "diagnostic-metadata/0.1"


@dataclass(frozen=True, slots=True)
class DiagnosticProjection:
    """Versioned metadata values reporters may serialize."""

    version: str
    profile: str | None
    provenance_ids: tuple[str, ...]
    properties: tuple[tuple[str, str], ...]


class _GeneratedProvenance(Protocol):
    """Structural input that keeps schema projection independent of fact storage."""

    @property
    def fact_id(self) -> str: ...

    @property
    def generated_document_id(self) -> str: ...

    @property
    def source_document_id(self) -> str | None: ...

    @property
    def source_kind(self) -> str | None: ...

    @property
    def conversion_stage(self) -> str | None: ...


class SchemaHost:
    """Own diagnostic metadata projection and generated-origin field naming."""

    _SUPPORTED_PROJECTION_VERSIONS = frozenset({DIAGNOSTIC_PROJECTION_VERSION})
    _RESERVED_PROPERTY_NAMES = frozenset(
        {"profile", "provenance", "provenanceIds", "provenance_ids"}
    )

    @classmethod
    def project_diagnostic(
        cls,
        diagnostic: Diagnostic,
        *,
        version: str = DIAGNOSTIC_PROJECTION_VERSION,
        profile: str | None = None,
        provenances: tuple[_GeneratedProvenance, ...] = (),
    ) -> DiagnosticProjection:
        if version not in cls._SUPPORTED_PROJECTION_VERSIONS:
            raise ValueError(f"unsupported diagnostic projection version: {version}")
        projected_profile = diagnostic.profile if profile is None else profile
        provenance_ids = tuple(dict.fromkeys(diagnostic.provenance_ids))
        provenances_by_id: dict[str, _GeneratedProvenance] = {}
        for provenance in provenances:
            provenances_by_id.setdefault(provenance.fact_id, provenance)
        unique_provenances = tuple(provenances_by_id.values())
        generated_properties: list[tuple[str, str]] = []
        if unique_provenances:
            provenance_ids = tuple(
                dict.fromkeys(
                    (*provenance_ids, *(provenance.fact_id for provenance in unique_provenances))
                )
            )
            for index, provenance in enumerate(unique_provenances, start=1):
                prefix = "" if len(unique_provenances) == 1 else f"provenance_{index}_"
                generated_properties.extend(
                    cls.generated_provenance_properties(provenance, prefix=prefix)
                )
        reserved_names = {
            *cls._RESERVED_PROPERTY_NAMES,
            *(name for name, _value in generated_properties),
        }
        rule_properties = dict(diagnostic.properties)
        properties = (
            *(
                (name, value)
                for name, value in rule_properties.items()
                if name not in reserved_names
            ),
            *generated_properties,
        )
        return DiagnosticProjection(
            version=version,
            profile=projected_profile,
            provenance_ids=provenance_ids,
            properties=properties,
        )

    @staticmethod
    def generated_provenance_properties(
        provenance: _GeneratedProvenance,
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
