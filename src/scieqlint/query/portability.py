"""Portability QueryView."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import CodeCellFact

_CROSSREF_PREFIXES = ("fig-", "tbl-", "eq-", "lst-")
_CROSSREF_OPTIONS = frozenset({"fig-cap", "tbl-cap", "lst-cap", "cap", "caption"})


@dataclass(frozen=True, slots=True)
class NotebookRenderingConflict:
    cell: CodeCellFact
    renderings: str
    crossref_options: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PortabilityQueryView:
    snapshot: FactSnapshot

    def risks(self, risk_kind: str | None = None) -> tuple[OutputPortabilityFact, ...]:
        """Return portability facts, optionally restricted to one risk kind."""

        if risk_kind is None:
            return self.snapshot.portability
        return tuple(fact for fact in self.snapshot.portability if fact.risk_kind == risk_kind)

    def inline_math_missing_alt(self) -> tuple[InlineMathFact, ...]:
        return tuple(
            fact
            for fact in self.snapshot.inline_math
            if fact.delimiter_kind != "plain-text" and fact.alt is None
        )

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

    def notebook_rendering_conflicts(self) -> tuple[NotebookRenderingConflict, ...]:
        conflicts: list[NotebookRenderingConflict] = []
        for cell in self.snapshot.code_cells:
            options = cell.option_dict()
            renderings = options.get("renderings")
            if renderings is None or not _cell_creates_crossref(cell):
                continue
            crossref_options = tuple(sorted(key for key in _CROSSREF_OPTIONS if key in options))
            if cell.label is not None and cell.label.lower().startswith(_CROSSREF_PREFIXES):
                crossref_options = ("label", *crossref_options)
            conflicts.append(
                NotebookRenderingConflict(
                    cell=cell,
                    renderings=renderings,
                    crossref_options=crossref_options,
                )
            )
        return tuple(conflicts)


def _cell_creates_crossref(cell: CodeCellFact) -> bool:
    options = cell.option_dict()
    if any(key in options for key in _CROSSREF_OPTIONS):
        return True
    return cell.label is not None and cell.label.lower().startswith(_CROSSREF_PREFIXES)
