"""Immutable fact snapshot and typed fact buckets."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.base import FactBase
from scieqlint.facts.generated import GeneratedFormulaFact, GeneratedProvenanceFact
from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.project import HiddenExcludedFact, ProjectMemberFact
from scieqlint.facts.reference import (
    CrossrefMetadataFact,
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    ReferenceDisplayTextFact,
    TargetAnchorFact,
)
from scieqlint.facts.structure import (
    CodeCellFact,
    DirectiveFact,
    FenceFact,
    HeadingFact,
    NotebookOutputFact,
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
    notebook_outputs: tuple[NotebookOutputFact, ...] = ()
    structure_syntax_issues: tuple[StructureSyntaxIssueFact, ...] = ()
    target_anchors: tuple[TargetAnchorFact, ...] = ()
    generic_refs: tuple[GenericRefFact, ...] = ()
    equation_labels: tuple[EquationLabelFact, ...] = ()
    equation_refs: tuple[EquationRefFact, ...] = ()
    crossref_metadata: tuple[CrossrefMetadataFact, ...] = ()
    reference_display_text: tuple[ReferenceDisplayTextFact, ...] = ()
    inline_math: tuple[InlineMathFact, ...] = ()
    display_math: tuple[DisplayMathFact, ...] = ()
    project_members: tuple[ProjectMemberFact, ...] = ()
    hidden_excluded: tuple[HiddenExcludedFact, ...] = ()
    generated_provenance: tuple[GeneratedProvenanceFact, ...] = ()
    generated_formulas: tuple[GeneratedFormulaFact, ...] = ()
    portability: tuple[OutputPortabilityFact, ...] = ()

    def all_facts(self) -> tuple[FactBase, ...]:
        return (
            *self.headings,
            *self.sections,
            *self.fences,
            *self.directives,
            *self.code_cells,
            *self.notebook_outputs,
            *self.structure_syntax_issues,
            *self.target_anchors,
            *self.generic_refs,
            *self.equation_labels,
            *self.equation_refs,
            *self.crossref_metadata,
            *self.reference_display_text,
            *self.inline_math,
            *self.display_math,
            *self.project_members,
            *self.hidden_excluded,
            *self.generated_provenance,
            *self.generated_formulas,
            *self.portability,
        )
