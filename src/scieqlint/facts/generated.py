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
    "placeholder",
    "empty-display",
    "image-placeholder",
    "equation-like-text",
]
GeneratedFormulaCandidateKind = Literal[
    "formula-text",
    "bracketed-block",
    "placeholder",
    "equation-like-text",
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
    candidate_kind: GeneratedFormulaCandidateKind | None = None
    source_math_fact_id: str | None = None
    placeholder_kind: str | None = None
    complete: bool | None = None

    def __post_init__(self) -> None:
        if (self.kind == "candidate") != (self.candidate_kind is not None):
            raise ValueError(
                "GeneratedFormulaFact candidate_kind must be set exactly for candidate facts"
            )
        expects_placeholder_kind = (
            self.kind == "candidate" and self.candidate_kind == "placeholder"
        ) or self.kind in {"placeholder", "empty-display", "image-placeholder"}
        if expects_placeholder_kind != (self.placeholder_kind is not None):
            raise ValueError(
                "GeneratedFormulaFact placeholder_kind does not match its artifact state"
            )
        expects_complete = (
            self.kind == "candidate"
            and (
                self.candidate_kind == "bracketed-block"
                or self.placeholder_kind == "empty-display-math"
            )
        ) or self.kind in {"bracketed-block", "empty-display"}
        if expects_complete != (self.complete is not None):
            raise ValueError("GeneratedFormulaFact complete does not match its artifact state")
