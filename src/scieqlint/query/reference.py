"""Reference QueryView."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TypeVar

from scieqlint.facts.reference import (
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    NormalizedReferenceTarget,
    TargetAnchorFact,
    generic_reference_identity,
    normalized_reference_target,
)
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.io.workspace import normalize_project_path

TargetFact = TargetAnchorFact | EquationLabelFact
TargetT = TypeVar("TargetT", bound=TargetFact)


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

    def target_index(self) -> dict[str, tuple[TargetFact, ...]]:
        """Return the label-only namespace used by pathless reference roles."""

        index: dict[str, list[TargetFact]] = defaultdict(list)
        for anchor in self.snapshot.target_anchors:
            if anchor.placement == "orphaned":
                continue
            index[anchor.normalized_label].append(anchor)
        for label in self.snapshot.equation_labels:
            index[label.normalized_label].append(label)
        return {key: tuple(value) for key, value in index.items()}

    def target_identity_index(
        self,
    ) -> dict[NormalizedReferenceTarget, tuple[TargetFact, ...]]:
        """Return targets keyed by normalized member path and label."""

        return self._target_identity_index(self._target_facts())

    def equation_target_index(self) -> dict[str, tuple[EquationLabelFact, ...]]:
        index: dict[str, list[EquationLabelFact]] = defaultdict(list)
        for label in self.snapshot.equation_labels:
            index[label.normalized_label].append(label)
        return {key: tuple(value) for key, value in index.items()}

    def duplicate_equation_targets(
        self,
    ) -> dict[str, tuple[EquationLabelFact, ...]]:
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

    def duplicate_generic_targets(
        self,
    ) -> dict[NormalizedReferenceTarget, tuple[TargetAnchorFact, ...]]:
        index = self._target_identity_index(
            tuple(
                anchor for anchor in self.snapshot.target_anchors if anchor.placement != "orphaned"
            )
        )
        return {key: tuple(value) for key, value in index.items() if len(value) > 1}

    def unresolved_generic_refs(self) -> tuple[GenericRefFact, ...]:
        targets = self.target_index()
        identity_targets = self.target_identity_index()
        return tuple(
            ref
            for ref in self.snapshot.generic_refs
            if generic_reference_identity(ref) is not None
            and not self._generic_ref_targets(ref, targets, identity_targets)
        )

    def ambiguous_generic_refs(self) -> tuple[GenericRefFact, ...]:
        targets = self.target_index()
        identity_targets = self.target_identity_index()
        return tuple(
            ref
            for ref in self.snapshot.generic_refs
            if generic_reference_identity(ref) is not None
            and len(self._generic_ref_targets(ref, targets, identity_targets)) > 1
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

        raw_member_index = {path: tuple(document_ids) for path, document_ids in raw_members.items()}
        normalized_member_index = {
            path: tuple(document_ids) for path, document_ids in normalized_members.items()
        }
        normalized_member_ids = {
            path: frozenset(document_ids) for path, document_ids in normalized_members.items()
        }

        mismatches: list[tuple[GenericRefFact, tuple[str, ...], tuple[str, ...]]] = []
        target_facts = self._target_facts()
        target_index = self._target_identity_index(target_facts)
        raw_target_index: dict[tuple[str, str], list[tuple[int, TargetFact]]] = defaultdict(list)
        for order, fact in enumerate(target_facts):
            raw_target_index[(fact.document_id, fact.normalized_label)].append((order, fact))
        normalized_target_cache: dict[NormalizedReferenceTarget, tuple[TargetFact, ...]] = {}
        mismatch_cache: dict[tuple[str, NormalizedReferenceTarget], bool] = {}
        for ref in self.snapshot.generic_refs:
            if ref.resolved_raw_target_path is None or ref.normalized_target_path is None:
                continue
            raw_matches = raw_member_index.get(ref.resolved_raw_target_path, ())
            normalized_path = ref.normalized_target_path.as_posix()
            normalized_matches = normalized_member_index.get(normalized_path, ())
            identity = normalized_reference_target(ref)
            normalized_targets = normalized_target_cache.get(identity)
            if normalized_targets is None:
                member_ids = normalized_member_ids.get(normalized_path, frozenset())
                normalized_targets = tuple(
                    fact
                    for fact in target_index.get(identity, ())
                    if fact.document_id in member_ids
                )
                normalized_target_cache[identity] = normalized_targets
            resolution = (ref.resolved_raw_target_path, identity)
            mismatch = mismatch_cache.get(resolution)
            if mismatch is None:
                raw_target_candidates = [
                    candidate
                    for document_id in dict.fromkeys(raw_matches)
                    for candidate in raw_target_index.get((document_id, identity[1]), ())
                ]
                raw_target_candidates.sort(key=lambda candidate: candidate[0])
                raw_targets = tuple(fact for _order, fact in raw_target_candidates)
                mismatch = raw_targets != normalized_targets and bool(normalized_targets)
                mismatch_cache[resolution] = mismatch
            if mismatch:
                mismatches.append((ref, raw_matches, normalized_matches))
        return tuple(mismatches)

    def _generic_ref_targets(
        self,
        ref: GenericRefFact,
        target_index: dict[str, tuple[TargetFact, ...]],
        identity_index: dict[NormalizedReferenceTarget, tuple[TargetFact, ...]],
    ) -> tuple[TargetFact, ...]:
        identity = generic_reference_identity(ref)
        assert identity is not None
        if isinstance(identity, tuple):
            return identity_index.get(identity, ())
        return target_index.get(identity, ())

    def _target_facts(self) -> tuple[TargetFact, ...]:
        return (
            *tuple(
                anchor for anchor in self.snapshot.target_anchors if anchor.placement != "orphaned"
            ),
            *self.snapshot.equation_labels,
        )

    def _target_identity_index(
        self,
        targets: tuple[TargetT, ...],
    ) -> dict[NormalizedReferenceTarget, tuple[TargetT, ...]]:
        member_paths = {
            member.document_id: member.normalized_path or member.path
            for member in self.snapshot.project_members
        }
        index: dict[NormalizedReferenceTarget, list[TargetT]] = defaultdict(list)
        for target in targets:
            member_path = member_paths.get(target.document_id)
            if member_path is None:
                member_path = normalize_project_path(target.document_id)
            identity = (member_path, target.normalized_label)
            index[identity].append(target)
        return {key: tuple(value) for key, value in index.items()}

    def orphaned_targets(self) -> tuple[TargetAnchorFact, ...]:
        return tuple(
            anchor for anchor in self.snapshot.target_anchors if anchor.placement == "orphaned"
        )
