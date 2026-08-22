"""Generated-document provenance and formula-quality facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scieqlint.facts.base import FactBase

GENERATED_PROVENANCE_FACT_SUFFIX = "::generated-provenance"
GeneratedFormulaKind = Literal[
    "candidate",
    "spaced-token",
    "garbled-marker",
    "bracketed-block",
]
GeneratedFormulaCandidateKind = Literal["formula-text", "bracketed-block"]
GeneratedBracketDelimiter = Literal["escaped", "literal"]


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
    candidate_kind: GeneratedFormulaCandidateKind | None = None
    source_math_fact_id: str | None = None
    complete: bool | None = None
    # Bracketed candidates and final facts retain the delimiter seen by the
    # scanner; formula-text and inferred artifact facts do not have one.
    delimiter_kind: GeneratedBracketDelimiter | None = None

    def __post_init__(self) -> None:
        if (self.kind == "candidate") != (self.candidate_kind is not None):
            raise ValueError("candidate formula facts must set candidate_kind")
        expects_complete = self.kind == "bracketed-block" or (
            self.kind == "candidate" and self.candidate_kind == "bracketed-block"
        )
        if expects_complete != (self.complete is not None):
            raise ValueError("bracketed formula facts must retain completeness metadata")
        if expects_complete != (self.delimiter_kind is not None):
            raise ValueError("bracketed formula facts must retain delimiter kind")
