"""Structure QueryView."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import (
    CodeCellFact,
    DirectiveFact,
    FenceFact,
    HeadingFact,
    SectionFact,
    StructureSyntaxIssueFact,
)


@dataclass(frozen=True, slots=True)
class StructureQueryView:
    snapshot: FactSnapshot

    def headings(self) -> tuple[HeadingFact, ...]:
        return self.snapshot.headings

    def sections(self) -> tuple[SectionFact, ...]:
        return self.snapshot.sections

    def fences(self) -> tuple[FenceFact, ...]:
        return self.snapshot.fences

    def directives(self) -> tuple[DirectiveFact, ...]:
        return self.snapshot.directives

    def code_cells(self) -> tuple[CodeCellFact, ...]:
        return self.snapshot.code_cells

    def syntax_issues(self) -> tuple[StructureSyntaxIssueFact, ...]:
        return self.snapshot.structure_syntax_issues

    def malformed_headings(self) -> tuple[HeadingFact, ...]:
        return tuple(heading for heading in self.snapshot.headings if not heading.valid_atx)

    def unclosed_fences(self) -> tuple[FenceFact, ...]:
        return tuple(fence for fence in self.snapshot.fences if not fence.is_closed)
