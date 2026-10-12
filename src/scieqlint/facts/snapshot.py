"""Immutable fact snapshot and typed fact buckets."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.generated import GeneratedFormulaFact, GeneratedProvenanceFact
from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.project import ProjectMemberFact
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
    FenceFact,
    HeadingFact,
    NotebookOutputFact,
    StructureSyntaxIssueFact,
)
from scieqlint.io.source import SourceDocument


@dataclass(frozen=True, slots=True)
class FactSnapshot:
    documents: tuple[SourceDocument, ...] = ()
    headings: tuple[HeadingFact, ...] = ()
    fences: tuple[FenceFact, ...] = ()
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
    generated_provenance: tuple[GeneratedProvenanceFact, ...] = ()
    generated_formulas: tuple[GeneratedFormulaFact, ...] = ()
    portability: tuple[OutputPortabilityFact, ...] = ()
