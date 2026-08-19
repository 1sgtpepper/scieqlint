"""Reference QueryView."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from scieqlint.facts.reference import (
    CrossrefMetadataFact,
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    TargetAnchorFact,
)
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

    def equation_refs(self) -> tuple[EquationRefFact, ...]:
        return self.snapshot.equation_refs

    def metadata_facts(self) -> tuple[CrossrefMetadataFact, ...]:
        return self.snapshot.crossref_metadata

    def conflicting_metadata(
        self,
    ) -> tuple[tuple[str, tuple[CrossrefMetadataFact, ...]], ...]:
        """Return targets with distinct metadata signatures across output boundaries."""

        by_target: dict[str, list[CrossrefMetadataFact]] = defaultdict(list)
        for fact in self.snapshot.crossref_metadata:
            if fact.metadata_kind != "target-definition":
                continue
            by_target[fact.normalized_target].append(fact)
        conflicts: list[tuple[str, tuple[CrossrefMetadataFact, ...]]] = []
        for target, facts in sorted(by_target.items()):
            boundaries = {fact.output_boundary for fact in facts}
            signatures = {_producer_signature(fact) for fact in facts}
            if len(boundaries) > 1 and len(signatures) > 1:
                conflicts.append((target, tuple(sorted(facts, key=_metadata_source_key))))
        return tuple(conflicts)

    def target_index(self) -> dict[str, tuple[TargetFact, ...]]:
        index: dict[str, list[TargetFact]] = defaultdict(list)
        for anchor in self.snapshot.target_anchors:
            if anchor.placement == "orphaned":
                continue
            index[anchor.normalized_label].append(anchor)
        for label in self.snapshot.equation_labels:
            index[label.normalized_label].append(label)
        return {key: tuple(value) for key, value in index.items()}

    def equation_target_index(self) -> dict[str, tuple[EquationLabelFact, ...]]:
        index: dict[str, list[EquationLabelFact]] = defaultdict(list)
        for label in self.snapshot.equation_labels:
            index[label.normalized_label].append(label)
        return {key: tuple(value) for key, value in index.items()}

    def duplicate_equation_targets(self) -> dict[str, tuple[EquationLabelFact, ...]]:
        return {key: value for key, value in self.equation_target_index().items() if len(value) > 1}

    def unresolved_equation_refs(self) -> tuple[EquationRefFact, ...]:
        targets = self.equation_target_index()
        return tuple(
            ref for ref in self.snapshot.equation_refs if ref.normalized_target not in targets
        )

    def ambiguous_equation_refs(self) -> tuple[EquationRefFact, ...]:
        targets = self.equation_target_index()
        return tuple(
            ref
            for ref in self.snapshot.equation_refs
            if len(targets.get(ref.normalized_target, ())) > 1
        )

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

    def path_normalization_mismatches(
        self,
    ) -> tuple[tuple[GenericRefFact, tuple[str, ...], tuple[str, ...]], ...]:
        """Return local path references whose raw and normalized resolution differ."""

        raw_members: dict[str, list[str]] = defaultdict(list)
        normalized_members: dict[str, list[str]] = defaultdict(list)
        for member in self.snapshot.project_members:
            raw_members[member.path.as_posix()].append(member.document_id)
            normalized = member.normalized_path or member.path
            normalized_members[normalized.as_posix()].append(member.document_id)

        mismatches: list[tuple[GenericRefFact, tuple[str, ...], tuple[str, ...]]] = []
        for ref in self.snapshot.generic_refs:
            if ref.resolved_raw_target_path is None or ref.normalized_target_path is None:
                continue
            raw_matches = tuple(raw_members.get(ref.resolved_raw_target_path, ()))
            normalized_matches = tuple(
                normalized_members.get(ref.normalized_target_path.as_posix(), ())
            )
            if raw_matches != normalized_matches and normalized_matches:
                mismatches.append((ref, raw_matches, normalized_matches))
        return tuple(mismatches)

    def orphaned_targets(self) -> tuple[TargetAnchorFact, ...]:
        return tuple(
            anchor for anchor in self.snapshot.target_anchors if anchor.placement == "orphaned"
        )


def _metadata_source_key(fact: CrossrefMetadataFact) -> tuple[str, int, int, str, str]:
    """Return a content-independent source order for conflict baselines."""

    span = fact.target_span or fact.span
    return (
        fact.document_id,
        span.start if span is not None else -1,
        span.end if span is not None else -1,
        fact.output_boundary,
        fact.fact_id,
    )


def _producer_signature(
    fact: CrossrefMetadataFact,
) -> tuple[str | None, tuple[tuple[str, str], ...]]:
    return (
        fact.resolved_target_kind or fact.reference_kind,
        tuple(sorted(fact.target_metadata or fact.display_metadata)),
    )
