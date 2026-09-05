"""Portability QueryView."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import CodeCellFact, NotebookOutputFact

_CROSSREF_PREFIXES = ("fig-", "tbl-", "eq-", "lst-")
_CROSSREF_OPTIONS = frozenset(
    {
        "cap",
        "caption",
        "fig-cap",
        "fig-subcap",
        "lst-cap",
        "tbl-cap",
        "tbl-subcap",
    }
)
_CROSSREF_LABEL_OPTIONS = frozenset({"label", "lst-label"})
_CROSSREF_LABEL_ORDER = ("label", "lst-label")


@dataclass(frozen=True, slots=True)
class NotebookRenderingConflict:
    cell: CodeCellFact
    renderings: str
    crossref_options: tuple[str, ...]
    output: NotebookOutputFact | None = None


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
            labels = tuple(
                label
                for label in (cell.label, cell.option_dict().get("lst-label"))
                if label is not None
            )
            if not labels:
                continue
            if not _cell_creates_crossref(cell):
                continue
            if any(not _has_crossref_prefix(label) for label in labels):
                bad.append(cell)
        return tuple(bad)

    def renderings_with_crossref_options(self) -> tuple[CodeCellFact, ...]:
        outputs = _outputs_by_cell(self.snapshot)
        out: list[CodeCellFact] = []
        for cell in self.snapshot.code_cells:
            options = cell.option_dict()
            if "renderings" in options and _crossref_options(cell, outputs.get(cell.fact_id, ())):
                out.append(cell)
        return tuple(out)

    def notebook_rendering_conflicts(self) -> tuple[NotebookRenderingConflict, ...]:
        outputs = _outputs_by_cell(self.snapshot)
        conflicts: list[NotebookRenderingConflict] = []
        for cell in self.snapshot.code_cells:
            options = cell.option_dict()
            renderings = options.get("renderings")
            if renderings is None:
                continue
            cell_outputs = outputs.get(cell.fact_id, ())
            cell_options = _cell_crossref_options(cell)
            output_conflicts: list[tuple[NotebookOutputFact, tuple[str, ...]]] = []
            for output in cell_outputs:
                output_options = _output_crossref_options(output)
                if output_options:
                    output_conflicts.append((output, output_options))
            if output_conflicts:
                for output, output_options in output_conflicts:
                    conflicts.append(
                        NotebookRenderingConflict(
                            cell=cell,
                            renderings=renderings,
                            crossref_options=_merge_crossref_options(
                                cell_options,
                                output_options,
                            ),
                            output=output,
                        )
                    )
            elif cell_options:
                conflicts.append(
                    NotebookRenderingConflict(
                        cell=cell,
                        renderings=renderings,
                        crossref_options=cell_options,
                    )
                )
        return tuple(conflicts)


def _cell_creates_crossref(cell: CodeCellFact) -> bool:
    options = cell.option_dict()
    if any(key in options for key in _CROSSREF_OPTIONS):
        return True
    return _has_crossref_prefix(cell.label) or _has_crossref_prefix(options.get("lst-label"))


def _has_crossref_prefix(label: str | None) -> bool:
    if label is None:
        return False
    return label.strip().removeprefix("#").startswith(_CROSSREF_PREFIXES)


def _outputs_by_cell(
    snapshot: FactSnapshot,
) -> dict[str, tuple[NotebookOutputFact, ...]]:
    grouped: dict[str, list[NotebookOutputFact]] = {}
    for output in snapshot.notebook_outputs:
        grouped.setdefault(output.cell_fact_id, []).append(output)
    return {cell_id: tuple(outputs) for cell_id, outputs in grouped.items()}


def _crossref_options(
    cell: CodeCellFact,
    outputs: tuple[NotebookOutputFact, ...],
) -> tuple[str, ...]:
    options = set(_cell_crossref_options(cell))
    for output in outputs:
        options.update(_output_crossref_options(output))
    return _ordered_crossref_options(options)


def _cell_crossref_options(cell: CodeCellFact) -> tuple[str, ...]:
    options = cell.option_dict()
    crossref_options = {key for key in _CROSSREF_OPTIONS if key in options}
    if _has_crossref_prefix(cell.label):
        crossref_options.add("label")
    if _has_crossref_prefix(options.get("lst-label")):
        crossref_options.add("lst-label")
    return _ordered_crossref_options(crossref_options)


def _output_crossref_options(output: NotebookOutputFact) -> tuple[str, ...]:
    metadata = dict(output.metadata)
    options = {key for key in _CROSSREF_OPTIONS if key in metadata}
    for key in _CROSSREF_LABEL_ORDER:
        label = metadata.get(key)
        if label is not None and label.strip():
            if _has_crossref_prefix(label):
                options.add(key)
            break
    return _ordered_crossref_options(options)


def _merge_crossref_options(
    cell_options: tuple[str, ...],
    output_options: tuple[str, ...],
) -> tuple[str, ...]:
    return _ordered_crossref_options(set(cell_options) | set(output_options))


def _ordered_crossref_options(options: set[str]) -> tuple[str, ...]:
    labels = tuple(key for key in _CROSSREF_LABEL_ORDER if key in options)
    return labels + tuple(sorted(options - _CROSSREF_LABEL_OPTIONS))
