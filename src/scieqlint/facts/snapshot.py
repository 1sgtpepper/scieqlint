"""Immutable fact snapshot and typed fact buckets."""

from __future__ import annotations

from dataclasses import dataclass, field

from scieqlint.facts.base import FactBase
from scieqlint.facts.generated import GeneratedProvenanceFact
from scieqlint.facts.math import DisplayMathFact, InlineMathFact, UnknownMathFact
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.project import HiddenExcludedFact, ProjectMemberFact
from scieqlint.facts.reference import (
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    TargetAnchorFact,
)
from scieqlint.facts.structure import (
    CodeCellFact,
    DirectiveFact,
    FenceFact,
    HeadingFact,
    SectionFact,
    StructureSyntaxIssueFact,
)
from scieqlint.io.source import SourceDocument


@dataclass(frozen=True, slots=True)
class FactSnapshot:
    documents: tuple[SourceDocument, ...] = ()
    headings: tuple[HeadingFact, ...] = ()
    sections: tuple[SectionFact, ...] = ()
    fences: tuple[FenceFact, ...] = ()
    directives: tuple[DirectiveFact, ...] = ()
    code_cells: tuple[CodeCellFact, ...] = ()
    structure_syntax_issues: tuple[StructureSyntaxIssueFact, ...] = ()
    target_anchors: tuple[TargetAnchorFact, ...] = ()
    generic_refs: tuple[GenericRefFact, ...] = ()
    equation_labels: tuple[EquationLabelFact, ...] = ()
    equation_refs: tuple[EquationRefFact, ...] = ()
    inline_math: tuple[InlineMathFact, ...] = ()
    display_math: tuple[DisplayMathFact, ...] = ()
    unknown_math: tuple[UnknownMathFact, ...] = ()
    project_members: tuple[ProjectMemberFact, ...] = ()
    hidden_excluded: tuple[HiddenExcludedFact, ...] = ()
    generated_provenance: tuple[GeneratedProvenanceFact, ...] = ()
    portability: tuple[OutputPortabilityFact, ...] = ()
    metadata: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def all_facts(self) -> tuple[FactBase, ...]:
        return (
            *self.headings,
            *self.sections,
            *self.fences,
            *self.directives,
            *self.code_cells,
            *self.structure_syntax_issues,
            *self.target_anchors,
            *self.generic_refs,
            *self.equation_labels,
            *self.equation_refs,
            *self.inline_math,
            *self.display_math,
            *self.unknown_math,
            *self.project_members,
            *self.hidden_excluded,
            *self.generated_provenance,
            *self.portability,
        )

    def with_unknown_math(self, unknown_math: tuple[UnknownMathFact, ...]) -> FactSnapshot:
        return FactSnapshot(
            documents=self.documents,
            headings=self.headings,
            sections=self.sections,
            fences=self.fences,
            directives=self.directives,
            code_cells=self.code_cells,
            structure_syntax_issues=self.structure_syntax_issues,
            target_anchors=self.target_anchors,
            generic_refs=self.generic_refs,
            equation_labels=self.equation_labels,
            equation_refs=self.equation_refs,
            inline_math=self.inline_math,
            display_math=self.display_math,
            unknown_math=(*self.unknown_math, *unknown_math),
            project_members=self.project_members,
            hidden_excluded=self.hidden_excluded,
            generated_provenance=self.generated_provenance,
            portability=self.portability,
            metadata=self.metadata,
        )
