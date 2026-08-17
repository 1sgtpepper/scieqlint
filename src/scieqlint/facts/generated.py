"""Generated-document provenance and formula-quality facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scieqlint.facts.base import FactBase

GeneratedFormulaKind = Literal[
    "candidate",
    "spaced-token",
    "garbled-marker",
    "bracketed-block",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class GeneratedProvenanceFact(FactBase):
    generated_document_id: str
    source_document_id: str | None = None
    source_kind: str | None = None
    conversion_stage: str | None = None
    source_sha: str | None = None
    tool: str | None = None
    tool_version: str | None = None
    preserved_anchor_inventory: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class GeneratedFormulaFact(FactBase):
    """One source-spanned formula artifact found in generated Markdown."""

    kind: GeneratedFormulaKind
    text: str
    source_math_fact_id: str | None = None
