"""Portability QueryView."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.math import InlineMathFact
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

    def risks(self) -> tuple[OutputPortabilityFact, ...]:
        return self.snapshot.portability

    def inline_math_missing_alt(self) -> tuple[InlineMathFact, ...]:
        return tuple(
            fact
            for fact in self.snapshot.inline_math
            if fact.delimiter_kind != "plain-text" and fact.alt is None
        )

    def notebook_rendering_conflicts(self) -> tuple[NotebookRenderingConflict, ...]:
        outputs = _outputs_by_cell(self.snapshot)
        conflicts: list[NotebookRenderingConflict] = []
        for cell in self.snapshot.code_cells:
            if cell.visibility != "visible":
                continue
            options = cell.option_dict()
            renderings = options.get("renderings")
            if renderings is None:
                continue
            cell_outputs = outputs.get(cell.fact_id, ())
            cell_crossref_options = {key for key in _CROSSREF_OPTIONS if key in options}
            if _has_crossref_prefix(cell.label):
                cell_crossref_options.add("label")
            if _has_crossref_prefix(options.get("lst-label")):
                cell_crossref_options.add("lst-label")
            cell_options = _ordered_crossref_options(cell_crossref_options)
            output_conflict_emitted = False
            for output in cell_outputs:
                output_options = _output_crossref_options(output)
                if output_options:
                    conflicts.append(
                        NotebookRenderingConflict(
                            cell=cell,
                            renderings=renderings,
                            crossref_options=_ordered_crossref_options(
                                set(cell_options) | set(output_options)
                            ),
                            output=output,
                        )
                    )
                    output_conflict_emitted = True
            if not output_conflict_emitted and cell_options:
                conflicts.append(
                    NotebookRenderingConflict(
                        cell=cell,
                        renderings=renderings,
                        crossref_options=cell_options,
                    )
                )
        return tuple(conflicts)


def _has_crossref_prefix(label: str | None) -> bool:
    if label is None:
        return False
    return label.strip().removeprefix("#").startswith(_CROSSREF_PREFIXES)


def _outputs_by_cell(
    snapshot: FactSnapshot,
) -> dict[str, list[NotebookOutputFact]]:
    grouped: dict[str, list[NotebookOutputFact]] = {}
    for output in snapshot.notebook_outputs:
        grouped.setdefault(output.cell_fact_id, []).append(output)
    return grouped


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


def _ordered_crossref_options(options: set[str]) -> tuple[str, ...]:
    labels = tuple(key for key in _CROSSREF_LABEL_ORDER if key in options)
    return labels + tuple(sorted(options - _CROSSREF_LABEL_OPTIONS))
