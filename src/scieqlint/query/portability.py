"""Portability QueryView."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import CodeCellFact

_CROSSREF_PREFIXES = ("fig-", "tbl-", "eq-", "lst-")
_CROSSREF_OPTIONS = frozenset({"fig-cap", "tbl-cap", "lst-cap", "cap", "caption"})


@dataclass(frozen=True, slots=True)
class PortabilityQueryView:
    snapshot: FactSnapshot

    def inline_math_missing_alt(self) -> tuple[InlineMathFact, ...]:
        return tuple(fact for fact in self.snapshot.inline_math if fact.alt is None)

    def display_math_missing_alt(self) -> tuple[DisplayMathFact, ...]:
        return tuple(fact for fact in self.snapshot.display_math if fact.alt is None)

    def quarto_crossref_label_issues(self) -> tuple[CodeCellFact, ...]:
        bad: list[CodeCellFact] = []
        for cell in self.snapshot.code_cells:
            if cell.label is None:
                continue
            if not _cell_creates_crossref(cell):
                continue
            if not cell.label.startswith(_CROSSREF_PREFIXES):
                bad.append(cell)
        return tuple(bad)

    def renderings_with_crossref_options(self) -> tuple[CodeCellFact, ...]:
        out: list[CodeCellFact] = []
        for cell in self.snapshot.code_cells:
            options = cell.option_dict()
            if "renderings" in options and _cell_creates_crossref(cell):
                out.append(cell)
        return tuple(out)


def _cell_creates_crossref(cell: CodeCellFact) -> bool:
    options = cell.option_dict()
    if any(key in options for key in _CROSSREF_OPTIONS):
        return True
    return cell.label is not None and cell.label.startswith(_CROSSREF_PREFIXES)
