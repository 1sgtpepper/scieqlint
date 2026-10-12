"""Reference QueryView."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypeVar, cast

from scieqlint.facts.reference import (
    CrossrefMetadataFact,
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    NormalizedReferenceTarget,
    ReferenceDisplayTextFact,
    TargetAnchorFact,
    crossref_target_identity,
    generic_reference_identity,
)
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import CodeCellFact
from scieqlint.io.workspace import normalize_project_path

TargetFact = TargetAnchorFact | EquationLabelFact | CodeCellFact
TargetT = TypeVar("TargetT", bound=TargetFact)


@dataclass(frozen=True, slots=True)
class NonvisibleEquationTargetImpact:
    reference: EquationRefFact
    visible_target_count: int
    hidden_target_count: int
    excluded_target_count: int
    hidden_example: EquationLabelFact | None
    excluded_example: EquationLabelFact | None


@dataclass(frozen=True, slots=True)
class UnclearReferenceDisplayText:
    fact: ReferenceDisplayTextFact
    reason: str


@dataclass(frozen=True, slots=True)
class _ReferenceQueryResults:
    target_identity_index: dict[NormalizedReferenceTarget, tuple[TargetFact, ...]]
    duplicate_equation_targets: dict[str, tuple[EquationLabelFact, ...]]
    duplicate_code_cell_targets: dict[NormalizedReferenceTarget, tuple[CodeCellFact, ...]]
    unresolved_equation_refs: tuple[EquationRefFact, ...]
    ambiguous_equation_refs: tuple[EquationRefFact, ...]
    nonvisible_equation_target_impacts: tuple[NonvisibleEquationTargetImpact, ...]
    unresolved_generic_refs: tuple[GenericRefFact, ...]
    ambiguous_generic_refs: tuple[GenericRefFact, ...]
    path_normalization_mismatches: tuple[
        tuple[GenericRefFact, tuple[str, ...], tuple[str, ...]], ...
    ]


@dataclass(frozen=True, slots=True)
class ReferenceQueryView:
    snapshot: FactSnapshot

    def visible_code_cell_targets(self) -> tuple[CodeCellFact, ...]:
        return tuple(
            cell
            for cell in self.snapshot.code_cells
            if cell.normalized_label is not None and cell.visibility == "visible"
        )

    def visible_equation_targets(self) -> tuple[EquationLabelFact, ...]:
        return tuple(
            label for label in self.snapshot.equation_labels if label.visibility == "visible"
        )

    def visible_generic_refs(self) -> tuple[GenericRefFact, ...]:
        return tuple(ref for ref in self.snapshot.generic_refs if ref.visibility == "visible")

    def visible_equation_refs(self) -> tuple[EquationRefFact, ...]:
        return tuple(ref for ref in self.snapshot.equation_refs if ref.visibility == "visible")

    def metadata_facts(self) -> tuple[CrossrefMetadataFact, ...]:
        if not self.snapshot.project_members:
            return self.snapshot.crossref_metadata
        visible_document_ids = frozenset(
            member.document_id
            for member in self.snapshot.project_members
            if member.visibility == "visible"
        )
        return tuple(
            fact
            for fact in self.snapshot.crossref_metadata
            if fact.document_id in visible_document_ids
        )

    def display_text_facts(self) -> tuple[ReferenceDisplayTextFact, ...]:
        if not self.snapshot.project_members:
            return self.snapshot.reference_display_text
        visible_document_ids = frozenset(
            member.document_id
            for member in self.snapshot.project_members
            if member.visibility == "visible"
        )
        return tuple(
            fact
            for fact in self.snapshot.reference_display_text
            if fact.document_id in visible_document_ids
        )

    def unclear_nonheading_display_text(
        self,
    ) -> tuple[UnclearReferenceDisplayText, ...]:
        """Return resolved non-heading references with missing or generic labels."""

        unclear: list[UnclearReferenceDisplayText] = []
        for fact in sorted(self.display_text_facts(), key=_display_source_key):
            if (
                fact.target_type in {None, "heading"}
                or fact.target_identity is None
                or fact.display_intent == "typed-number"
            ):
                continue
            reason = _unclear_display_reason(fact)
            if reason is not None:
                unclear.append(UnclearReferenceDisplayText(fact=fact, reason=reason))
        return tuple(unclear)

    def conflicting_metadata(
        self,
    ) -> tuple[tuple[NormalizedReferenceTarget, tuple[CrossrefMetadataFact, ...]], ...]:
        """Return targets with distinct metadata signatures across output boundaries."""

        by_target: dict[NormalizedReferenceTarget, list[CrossrefMetadataFact]] = defaultdict(list)
        for fact in self.metadata_facts():
            if fact.metadata_kind != "target-definition":
                continue
            identity = crossref_target_identity(fact)
            if identity is None:
                continue
            by_target[identity].append(fact)
        conflicts: list[tuple[NormalizedReferenceTarget, tuple[CrossrefMetadataFact, ...]]] = []
        for target, facts in sorted(
            by_target.items(), key=lambda item: (item[0][0].as_posix(), item[0][1])
        ):
            boundaries = {fact.output_boundary for fact in facts}
            signatures = {(fact.resolved_target_kind, fact.target_metadata) for fact in facts}
            if len(boundaries) > 1 and len(signatures) > 1:
                conflicts.append((target, tuple(sorted(facts, key=_metadata_source_key))))
        return tuple(conflicts)

    def results(self) -> _ReferenceQueryResults:
        visible_equation_index = _equation_index(self.visible_equation_targets())
        duplicate_equation_targets = {
            key: tuple(sorted(value, key=_query_fact_source_key))
            for key, value in sorted(
                visible_equation_index.items(),
                key=lambda item: _query_fact_source_key(item[1][0]),
            )
            if len(value) > 1
        }

        target_facts = self._target_facts()
        target_index, target_identity_index = self._target_indexes(target_facts)
        generic_ref_identities = tuple(
            (ref, generic_reference_identity(ref)) for ref in self.visible_generic_refs()
        )

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
        path_identities = {
            identity
            for ref, identity in generic_ref_identities
            if ref.resolved_raw_target_path is not None
            and ref.normalized_target_path is not None
            and isinstance(identity, tuple)
        }
        normalized_target_cache: dict[NormalizedReferenceTarget, tuple[TargetFact, ...]] = {}
        duplicate_code_cell_targets: dict[NormalizedReferenceTarget, tuple[CodeCellFact, ...]] = {}
        for identity, facts in sorted(
            target_identity_index.items(),
            key=lambda item: (item[0][0].as_posix(), item[0][1]),
        ):
            has_path_reference = identity in path_identities
            if len(facts) < 2 and not has_path_reference:
                continue
            cells: list[CodeCellFact] = []
            normalized_member_targets: list[TargetFact] = []
            member_ids: frozenset[str] = (
                normalized_member_ids.get(identity[0].as_posix(), frozenset())
                if has_path_reference
                else frozenset()
            )
            # Share this identity-bucket pass between duplicate-cell and path checks.
            for fact in facts:
                if isinstance(fact, CodeCellFact):
                    cells.append(fact)
                if has_path_reference and fact.document_id in member_ids:
                    normalized_member_targets.append(fact)
            if has_path_reference:
                normalized_target_cache[identity] = tuple(normalized_member_targets)
            if len(facts) >= 2 and cells:
                cells.sort(key=_code_cell_source_key)
                non_cell_count = len(facts) - len(cells)
                duplicates = cells if non_cell_count else cells[1:]
                duplicate_code_cell_targets[identity] = tuple(duplicates)

        hidden_equation_targets = _equation_target_summaries(
            label for label in self.snapshot.equation_labels if label.visibility == "hidden"
        )
        excluded_equation_targets = _equation_target_summaries(
            label for label in self.snapshot.equation_labels if label.visibility == "excluded"
        )
        visible_equation_refs = self.visible_equation_refs()
        nonvisible_impacts: list[NonvisibleEquationTargetImpact] = []
        unresolved_equation_refs: list[EquationRefFact] = []
        ambiguous_equation_refs: list[EquationRefFact] = []
        for ref in visible_equation_refs:
            visible_targets = visible_equation_index.get(ref.normalized_target, ())
            if not visible_targets:
                unresolved_equation_refs.append(ref)
            elif len(visible_targets) > 1:
                ambiguous_equation_refs.append(ref)
            hidden_summary = hidden_equation_targets.get(ref.normalized_target)
            excluded_summary = excluded_equation_targets.get(ref.normalized_target)
            if hidden_summary is not None or excluded_summary is not None:
                nonvisible_impacts.append(
                    NonvisibleEquationTargetImpact(
                        reference=ref,
                        visible_target_count=len(visible_targets),
                        hidden_target_count=hidden_summary[0] if hidden_summary else 0,
                        excluded_target_count=excluded_summary[0] if excluded_summary else 0,
                        hidden_example=hidden_summary[1] if hidden_summary else None,
                        excluded_example=excluded_summary[1] if excluded_summary else None,
                    )
                )
        nonvisible_impacts.sort(key=lambda impact: _query_fact_source_key(impact.reference))

        raw_target_index: dict[tuple[str, str], list[tuple[int, TargetFact]]] = defaultdict(list)
        for order, fact in enumerate(target_facts):
            normalized_label = cast(str, fact.normalized_label)
            raw_target_index[(fact.document_id, normalized_label)].append((order, fact))
        mismatch_cache: dict[tuple[str, NormalizedReferenceTarget], bool] = {}
        unresolved_generic_refs: list[GenericRefFact] = []
        ambiguous_generic_refs: list[GenericRefFact] = []
        path_normalization_mismatches: list[
            tuple[GenericRefFact, tuple[str, ...], tuple[str, ...]]
        ] = []
        for ref, identity in generic_ref_identities:
            if identity is not None:
                targets = (
                    target_identity_index.get(identity, ())
                    if isinstance(identity, tuple)
                    else target_index.get(identity, ())
                )
                if not targets:
                    unresolved_generic_refs.append(ref)
                elif len(targets) > 1:
                    ambiguous_generic_refs.append(ref)

            if ref.resolved_raw_target_path is None or ref.normalized_target_path is None:
                continue
            assert isinstance(identity, tuple)
            raw_matches = raw_member_index.get(ref.resolved_raw_target_path, ())
            normalized_path = ref.normalized_target_path.as_posix()
            normalized_matches = normalized_member_index.get(normalized_path, ())
            normalized_targets = normalized_target_cache.get(identity, ())
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
                path_normalization_mismatches.append((ref, raw_matches, normalized_matches))

        unresolved_equation_refs.sort(key=_query_fact_source_key)
        ambiguous_equation_refs.sort(key=_query_fact_source_key)
        unresolved_generic_refs.sort(key=_query_fact_source_key)
        ambiguous_generic_refs.sort(key=_query_fact_source_key)
        path_normalization_mismatches.sort(key=lambda item: _query_fact_source_key(item[0]))
        return _ReferenceQueryResults(
            target_identity_index=target_identity_index,
            duplicate_equation_targets=duplicate_equation_targets,
            duplicate_code_cell_targets=duplicate_code_cell_targets,
            unresolved_equation_refs=tuple(unresolved_equation_refs),
            ambiguous_equation_refs=tuple(ambiguous_equation_refs),
            nonvisible_equation_target_impacts=tuple(nonvisible_impacts),
            unresolved_generic_refs=tuple(unresolved_generic_refs),
            ambiguous_generic_refs=tuple(ambiguous_generic_refs),
            path_normalization_mismatches=tuple(path_normalization_mismatches),
        )

    def _target_facts(self) -> tuple[TargetFact, ...]:
        return (
            *(
                anchor
                for anchor in self.snapshot.target_anchors
                if anchor.visibility == "visible" and anchor.placement != "orphaned"
            ),
            *self.visible_equation_targets(),
            *self.visible_code_cell_targets(),
        )

    def _target_indexes(
        self,
        targets: tuple[TargetT, ...],
    ) -> tuple[
        dict[str, tuple[TargetT, ...]],
        dict[NormalizedReferenceTarget, tuple[TargetT, ...]],
    ]:
        member_paths = {
            member.document_id: member.normalized_path or member.path
            for member in self.snapshot.project_members
        }
        label_index: dict[str, list[TargetT]] = defaultdict(list)
        identity_index: dict[NormalizedReferenceTarget, list[TargetT]] = defaultdict(list)
        for target in targets:
            normalized_label = cast(str, target.normalized_label)
            label_index[normalized_label].append(target)
            if target.document_id not in member_paths:
                member_paths[target.document_id] = normalize_project_path(target.document_id)
            identity = (member_paths[target.document_id], normalized_label)
            identity_index[identity].append(target)
        return (
            {key: tuple(value) for key, value in label_index.items()},
            {key: tuple(value) for key, value in identity_index.items()},
        )


def _equation_index(
    labels: tuple[EquationLabelFact, ...],
) -> dict[str, tuple[EquationLabelFact, ...]]:
    index: dict[str, list[EquationLabelFact]] = defaultdict(list)
    for label in labels:
        index[label.normalized_label].append(label)
    return {key: tuple(value) for key, value in index.items()}


def _equation_target_summaries(
    labels: Iterable[EquationLabelFact],
) -> dict[str, tuple[int, EquationLabelFact]]:
    summaries: dict[str, tuple[int, EquationLabelFact]] = {}
    for label in labels:
        count, example = summaries.get(label.normalized_label, (0, label))
        if count == 0 or _equation_label_source_key(label) < _equation_label_source_key(example):
            example = label
        summaries[label.normalized_label] = (count + 1, example)
    return summaries


def _equation_label_source_key(fact: EquationLabelFact) -> tuple[str, int, int, str]:
    span = fact.label_span or fact.span
    return (
        fact.document_id,
        span.start if span is not None else -1,
        span.end if span is not None else -1,
        fact.fact_id,
    )


def _query_fact_source_key(
    fact: EquationLabelFact | EquationRefFact | GenericRefFact,
) -> tuple[str, int, int, int, str, str]:
    span = (
        fact.label_span or fact.span
        if isinstance(fact, EquationLabelFact)
        else fact.target_span or fact.span
    )
    return (
        fact.document_id,
        -1 if span is None or span.cell is None else span.cell,
        -1 if span is None else span.start,
        -1 if span is None else span.end,
        fact.fact_id,
        fact.raw or "",
    )


def _code_cell_source_key(fact: CodeCellFact) -> tuple[str, int, int, str]:
    span = fact.label_span or fact.span
    return (
        fact.document_id,
        span.start if span is not None else -1,
        span.end if span is not None else -1,
        fact.fact_id,
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


def _unclear_display_reason(fact: ReferenceDisplayTextFact) -> str | None:
    text = fact.explicit_text
    if text is None or not text.strip():
        return "missing"
    normalized = " ".join(text.casefold().split()).strip(" .:#-_[]()")
    target = " ".join(fact.normalized_target.casefold().split()).strip(" .:#-_[]()")
    target_type = (fact.target_type or "").casefold()
    generic = {
        target,
        target_type,
        "reference",
        "link",
        "this",
        "here",
        f"{target_type} reference",
    }
    if target_type == "block":
        generic.add("paragraph")
    return "generic" if normalized in generic else None


def _display_source_key(
    fact: ReferenceDisplayTextFact,
) -> tuple[str, int, int, str]:
    span = fact.display_text_span or fact.span
    return (
        fact.document_id,
        span.start if span is not None else -1,
        span.end if span is not None else -1,
        fact.fact_id,
    )
