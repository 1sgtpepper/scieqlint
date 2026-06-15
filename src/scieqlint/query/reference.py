"""Reference QueryView."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from scieqlint.facts.reference import EquationLabelFact, GenericRefFact, TargetAnchorFact
from scieqlint.facts.snapshot import FactSnapshot

TargetFact = TargetAnchorFact | EquationLabelFact


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    key: str
    facts: tuple[TargetFact, ...]


@dataclass(frozen=True, slots=True)
class ReferenceQueryView:
    snapshot: FactSnapshot

    def generic_targets(self) -> tuple[TargetAnchorFact, ...]:
        return self.snapshot.target_anchors

    def equation_targets(self) -> tuple[EquationLabelFact, ...]:
        return self.snapshot.equation_labels

    def generic_refs(self) -> tuple[GenericRefFact, ...]:
        return self.snapshot.generic_refs

    def target_index(self) -> dict[str, tuple[TargetFact, ...]]:
        index: dict[str, list[TargetFact]] = defaultdict(list)
        for anchor in self.snapshot.target_anchors:
            if anchor.placement == "orphaned":
                continue
            index[anchor.normalized_label].append(anchor)
        for label in self.snapshot.equation_labels:
            index[label.normalized_label].append(label)
        return {key: tuple(value) for key, value in index.items()}

    def duplicate_generic_targets(self) -> dict[str, tuple[TargetAnchorFact, ...]]:
        index: dict[str, list[TargetAnchorFact]] = defaultdict(list)
        for anchor in self.snapshot.target_anchors:
            index[anchor.normalized_label].append(anchor)
        return {key: tuple(value) for key, value in index.items() if len(value) > 1}

    def unresolved_generic_refs(self) -> tuple[GenericRefFact, ...]:
        targets = self.target_index()
        return tuple(
            ref for ref in self.snapshot.generic_refs if ref.normalized_target not in targets
        )

    def ambiguous_generic_refs(self) -> tuple[GenericRefFact, ...]:
        targets = self.target_index()
        return tuple(
            ref
            for ref in self.snapshot.generic_refs
            if len(targets.get(ref.normalized_target, ())) > 1
        )

    def orphaned_targets(self) -> tuple[TargetAnchorFact, ...]:
        return tuple(
            anchor for anchor in self.snapshot.target_anchors if anchor.placement == "orphaned"
        )
