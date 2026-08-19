"""Structure QueryView."""

from __future__ import annotations

import re
from dataclasses import dataclass

from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import (
    CodeCellFact,
    DirectiveFact,
    FenceFact,
    HeadingFact,
    NotebookOutputFact,
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

    def notebook_outputs(self) -> tuple[NotebookOutputFact, ...]:
        return self.snapshot.notebook_outputs

    def syntax_issues(self) -> tuple[StructureSyntaxIssueFact, ...]:
        return self.snapshot.structure_syntax_issues

    def unclosed_fences(self) -> tuple[FenceFact, ...]:
        return tuple(fence for fence in self.snapshot.fences if not fence.is_closed)

    def missing_code_cell_languages(self) -> tuple[CodeCellFact, ...]:
        return tuple(cell for cell in self.snapshot.code_cells if not cell.language)

    def invalid_code_cell_languages(self) -> tuple[CodeCellFact, ...]:
        """Return code-cell languages that are not syntactically valid identifiers.

        This check intentionally does not maintain an execution-language
        allowlist. A language can be valid metadata even when this linter does
        not execute or otherwise understand it.
        """

        return tuple(
            cell
            for cell in self.snapshot.code_cells
            if cell.language is not None and _CODE_CELL_LANGUAGE_RE.fullmatch(cell.language) is None
        )


_CODE_CELL_LANGUAGE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.+\-]*")
