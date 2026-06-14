"""DocumentIR contracts used between FrontendHost and FactHost."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.base import FactBase
from scieqlint.io.source import SourceDocument


@dataclass(frozen=True, slots=True)
class DocumentIR:
    document_id: str
    document: SourceDocument
    facts: tuple[FactBase, ...]


@dataclass(frozen=True, slots=True)
class FrontendResult:
    documents: tuple[DocumentIR, ...]
