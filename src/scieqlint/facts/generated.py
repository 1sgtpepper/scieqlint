"""Generated-document provenance facts."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.base import FactBase


@dataclass(frozen=True, slots=True, kw_only=True)
class GeneratedProvenanceFact(FactBase):
    generated_document_id: str
    source_document_id: str
    source_sha: str | None = None
    tool: str | None = None
    tool_version: str | None = None
    preserved_anchor_inventory: tuple[str, ...] = ()
