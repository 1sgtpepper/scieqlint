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
GeneratedPlaceholderKind = Literal[
    "formula-not-decoded",
    "empty-display-math",
    "formula-image",
]
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
    placeholder_kind: GeneratedPlaceholderKind | None = None
    complete: bool | None = None
    # Bracketed candidates and final facts retain the delimiter seen by the
    # scanner; formula-text and inferred artifact facts do not have one.
    delimiter_kind: GeneratedBracketDelimiter | None = None

    def __post_init__(self) -> None:
        if (self.kind == "candidate") != (self.candidate_kind is not None):
            raise ValueError(
                "GeneratedFormulaFact candidate_kind must be set exactly for candidate facts"
            )
        requires_source_math_fact_id = self.kind == "equation-like-text" or (
            self.kind == "candidate" and self.candidate_kind == "equation-like-text"
        )
        if requires_source_math_fact_id and self.source_math_fact_id is None:
            raise ValueError("GeneratedFormulaFact equation-like-text requires source_math_fact_id")
        expects_placeholder_kind = (
            self.kind == "candidate" and self.candidate_kind == "placeholder"
        ) or self.kind in {"placeholder", "empty-display", "image-placeholder"}
        if expects_placeholder_kind != (self.placeholder_kind is not None):
            raise ValueError(
                "GeneratedFormulaFact placeholder_kind does not match its artifact state"
            )
        expected_placeholder_kind = {
            "placeholder": "formula-not-decoded",
            "empty-display": "empty-display-math",
            "image-placeholder": "formula-image",
        }.get(self.kind)
        if (
            expected_placeholder_kind is not None
            and self.placeholder_kind != expected_placeholder_kind
        ):
            raise ValueError(
                f"GeneratedFormulaFact {self.kind} requires placeholder_kind "
                f"{expected_placeholder_kind}"
            )
        expects_bracketed = self.kind == "bracketed-block" or (
            self.kind == "candidate" and self.candidate_kind == "bracketed-block"
        )
        expects_complete = (
            (self.kind == "candidate" and self.placeholder_kind == "empty-display-math")
            or self.kind == "empty-display"
            or expects_bracketed
        )
        if expects_complete != (self.complete is not None):
            raise ValueError(
                "GeneratedFormulaFact completeness metadata does not match its artifact state"
            )
        if expects_bracketed != (self.delimiter_kind is not None):
            raise ValueError("bracketed formula facts must retain delimiter kind")
        if self.placeholder_kind == "empty-display-math" and self.complete is not True:
            raise ValueError("GeneratedFormulaFact empty-display-math requires complete=True")
