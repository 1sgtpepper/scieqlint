"""Reference QueryView."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath

from scieqlint.facts.reference import (
    CrossrefMetadataFact,
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    ReferenceDisplayTextFact,
    TargetAnchorFact,
    normalized_reference_target,
)
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import CodeCellFact

TargetFact = TargetAnchorFact | EquationLabelFact | CodeCellFact


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    key: str
    facts: tuple[TargetFact, ...]


@dataclass(frozen=True, slots=True)
class NonvisibleEquationTargetImpact:
    reference: EquationRefFact
    visible_targets: tuple[EquationLabelFact, ...]
    hidden_targets: tuple[EquationLabelFact, ...]
    excluded_targets: tuple[EquationLabelFact, ...]


@dataclass(frozen=True, slots=True)
class UnclearReferenceDisplayText:
    fact: ReferenceDisplayTextFact
    reason: str


@dataclass(frozen=True, slots=True)
class ReferenceQueryView:
    snapshot: FactSnapshot

    def generic_targets(self) -> tuple[TargetAnchorFact, ...]:
        return self.snapshot.target_anchors

    def equation_targets(self) -> tuple[EquationLabelFact, ...]:
        return self.snapshot.equation_labels

    def code_cell_targets(self) -> tuple[CodeCellFact, ...]:
        return tuple(cell for cell in self.snapshot.code_cells if cell.normalized_label is not None)

    def visible_code_cell_targets(self) -> tuple[CodeCellFact, ...]:
        return tuple(
            cell for cell in self.code_cell_targets() if cell.visibility == "visible"
        )

    def hidden_code_cell_targets(self) -> tuple[CodeCellFact, ...]:
        return tuple(cell for cell in self.code_cell_targets() if cell.visibility == "hidden")

    def excluded_code_cell_targets(self) -> tuple[CodeCellFact, ...]:
        return tuple(
            cell for cell in self.code_cell_targets() if cell.visibility == "excluded"
        )

    def visible_equation_targets(self) -> tuple[EquationLabelFact, ...]:
        return tuple(
            label
            for label in self.snapshot.equation_labels
            if label.visibility == "visible" and self._document_is_visible(label.document_id)
        )

    def hidden_equation_targets(self) -> tuple[EquationLabelFact, ...]:
        return tuple(
            label
            for label in self.snapshot.equation_labels
            if label.visibility == "hidden"
            or self._document_visibility(label.document_id) == "hidden"
        )

    def excluded_equation_targets(self) -> tuple[EquationLabelFact, ...]:
        return tuple(
            label
            for label in self.snapshot.equation_labels
            if label.visibility == "excluded"
            or self._document_visibility(label.document_id) == "excluded"
        )

    def generic_refs(self) -> tuple[GenericRefFact, ...]:
        return self.snapshot.generic_refs

    def equation_refs(self) -> tuple[EquationRefFact, ...]:
        return self.snapshot.equation_refs

    def visible_equation_refs(self) -> tuple[EquationRefFact, ...]:
        return tuple(ref for ref in self.snapshot.equation_refs if ref.visibility == "visible")

    def visible_generic_refs(self) -> tuple[GenericRefFact, ...]:
        return tuple(ref for ref in self.snapshot.generic_refs if ref.visibility == "visible")

    def metadata_facts(self) -> tuple[CrossrefMetadataFact, ...]:
        """Return visible source-owned target-definition metadata."""

        return tuple(
            fact
            for fact in self.snapshot.crossref_metadata
            if self._document_is_visible(fact.document_id)
        )

    def display_text_facts(self) -> tuple[ReferenceDisplayTextFact, ...]:
        return tuple(
            fact
            for fact in self.snapshot.reference_display_text
            if self._document_is_visible(fact.document_id)
        )

    def unclear_nonheading_display_text(
        self,
    ) -> tuple[UnclearReferenceDisplayText, ...]:
        """Return resolved non-heading references with missing or generic labels."""

        unclear: list[UnclearReferenceDisplayText] = []
        for fact in sorted(self.display_text_facts(), key=_display_source_key):
            if fact.target_type in {None, "heading"} or fact.display_intent == "typed-number":
                continue
            reason = _unclear_display_reason(fact)
            if reason is not None:
                unclear.append(UnclearReferenceDisplayText(fact=fact, reason=reason))
        return tuple(unclear)

    def conflicting_metadata(
        self,
    ) -> tuple[tuple[str, tuple[CrossrefMetadataFact, ...]], ...]:
        """Return target definitions with distinct signatures across output boundaries."""

        by_target: dict[str, list[CrossrefMetadataFact]] = defaultdict(list)
        for fact in self.metadata_facts():
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
            if (
                anchor.visibility != "visible"
                or anchor.placement == "orphaned"
                or not self._document_is_visible(anchor.document_id)
            ):
                continue
            index[anchor.normalized_label].append(anchor)
        for label in self.visible_equation_targets():
            index[label.normalized_label].append(label)
        for cell in self.visible_code_cell_targets():
            if not self._document_is_visible(cell.document_id):
                continue
            assert cell.normalized_label is not None
            index[cell.normalized_label].append(cell)
        return {key: tuple(value) for key, value in index.items()}

    def equation_target_index(self) -> dict[str, tuple[EquationLabelFact, ...]]:
        return _equation_index(self.visible_equation_targets())

    def hidden_equation_target_index(self) -> dict[str, tuple[EquationLabelFact, ...]]:
        return _equation_index(self.hidden_equation_targets())

    def excluded_equation_target_index(
        self,
    ) -> dict[str, tuple[EquationLabelFact, ...]]:
        return _equation_index(self.excluded_equation_targets())

    def duplicate_equation_targets(self) -> dict[str, tuple[EquationLabelFact, ...]]:
        return {key: value for key, value in self.equation_target_index().items() if len(value) > 1}

    def unresolved_equation_refs(self) -> tuple[EquationRefFact, ...]:
        targets = self.equation_target_index()
        return tuple(
            ref for ref in self.visible_equation_refs() if ref.normalized_target not in targets
        )

    def ambiguous_equation_refs(self) -> tuple[EquationRefFact, ...]:
        targets = self.equation_target_index()
        return tuple(
            ref
            for ref in self.visible_equation_refs()
            if len(targets.get(ref.normalized_target, ())) > 1
        )

    def nonvisible_equation_target_impacts(
        self,
    ) -> tuple[NonvisibleEquationTargetImpact, ...]:
        """Return references whose target identity exists outside the visible set."""

        visible = self.equation_target_index()
        hidden = self.hidden_equation_target_index()
        excluded = self.excluded_equation_target_index()
        impacts: list[NonvisibleEquationTargetImpact] = []
        for ref in sorted(self.visible_equation_refs(), key=_reference_source_key):
            hidden_targets = tuple(
                sorted(hidden.get(ref.normalized_target, ()), key=_equation_label_source_key)
            )
            excluded_targets = tuple(
                sorted(
                    excluded.get(ref.normalized_target, ()),
                    key=_equation_label_source_key,
                )
            )
            if not hidden_targets and not excluded_targets:
                continue
            impacts.append(
                NonvisibleEquationTargetImpact(
                    reference=ref,
                    visible_targets=visible.get(ref.normalized_target, ()),
                    hidden_targets=hidden_targets,
                    excluded_targets=excluded_targets,
                )
            )
        return tuple(impacts)

    def duplicate_generic_targets(self) -> dict[str, tuple[TargetAnchorFact, ...]]:
        index: dict[str, list[TargetAnchorFact]] = defaultdict(list)
        for anchor in self.generic_targets():
            if anchor.visibility != "visible":
                continue
            index[anchor.normalized_label].append(anchor)
        return {key: tuple(value) for key, value in index.items() if len(value) > 1}

    def duplicate_code_cell_targets(self) -> dict[str, tuple[CodeCellFact, ...]]:
        duplicates: dict[str, tuple[CodeCellFact, ...]] = {}
        for key, facts in self.target_index().items():
            if len(facts) < 2:
                continue
            cells = tuple(
                sorted(
                    (fact for fact in facts if isinstance(fact, CodeCellFact)),
                    key=_code_cell_source_key,
                )
            )
            if not cells:
                continue
            non_cell_count = len(facts) - len(cells)
            offending = cells if non_cell_count else cells[1:]
            duplicates[key] = offending
        return duplicates

    def unresolved_generic_refs(self) -> tuple[GenericRefFact, ...]:
        targets = self.target_index()
        return tuple(
            ref
            for ref in self.visible_generic_refs()
            if not self._generic_ref_targets(ref, targets)
        )

    def ambiguous_generic_refs(self) -> tuple[GenericRefFact, ...]:
        targets = self.target_index()
        return tuple(
            ref
            for ref in self.visible_generic_refs()
            if len(self._generic_ref_targets(ref, targets)) > 1
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
        target_index = self.target_index()
        for ref in self.visible_generic_refs():
            if ref.resolved_raw_target_path is None or ref.normalized_target_path is None:
                continue
            identity = normalized_reference_target(ref)
            if identity is None:
                continue
            raw_matches = tuple(raw_members.get(ref.resolved_raw_target_path, ()))
            normalized_matches = tuple(
                normalized_members.get(ref.normalized_target_path.as_posix(), ())
            )
            normalized_targets = tuple(
                fact
                for fact in target_index.get(identity[1], ())
                if fact.document_id in normalized_matches
            )
            raw_targets = tuple(
                fact
                for fact in target_index.get(identity[1], ())
                if fact.document_id in raw_matches
            )
            if raw_targets != normalized_targets and normalized_targets:
                mismatches.append((ref, raw_matches, normalized_matches))
        return tuple(mismatches)

    def _generic_ref_targets(
        self,
        ref: GenericRefFact,
        target_index: dict[str, tuple[TargetFact, ...]],
    ) -> tuple[TargetFact, ...]:
        if ref.normalized_target_path is None:
            return target_index.get(ref.normalized_target, ())
        identity = normalized_reference_target(ref)
        if identity is None:
            return ()
        member_ids = self._member_document_ids(identity[0])
        if not member_ids:
            return ()
        return tuple(
            target
            for target in target_index.get(identity[1], ())
            if target.document_id in member_ids
        )

    def _member_document_ids(self, normalized_path: PurePosixPath) -> frozenset[str]:
        return frozenset(
            member.document_id
            for member in self.snapshot.project_members
            if (member.normalized_path or member.path) == normalized_path
            and self._document_is_visible(member.document_id)
        )

    def _document_visibility(self, document_id: str) -> str:
        for member in self.snapshot.project_members:
            if member.document_id != document_id:
                continue
            return member.visibility
        return "visible"

    def _document_is_visible(self, document_id: str) -> bool:
        return self._document_visibility(document_id) == "visible"

    def orphaned_targets(self) -> tuple[TargetAnchorFact, ...]:
        return tuple(
            anchor for anchor in self.snapshot.target_anchors if anchor.placement == "orphaned"
        )


def _equation_index(
    labels: tuple[EquationLabelFact, ...],
) -> dict[str, tuple[EquationLabelFact, ...]]:
    index: dict[str, list[EquationLabelFact]] = defaultdict(list)
    for label in labels:
        index[label.normalized_label].append(label)
    return {key: tuple(value) for key, value in index.items()}


def _equation_label_source_key(
    fact: EquationLabelFact,
) -> tuple[str, int, int, str]:
    span = fact.label_span or fact.span
    return (
        fact.document_id,
        span.start if span is not None else -1,
        span.end if span is not None else -1,
        fact.fact_id,
    )


def _reference_source_key(fact: EquationRefFact) -> tuple[str, int, int, str]:
    span = fact.target_span or fact.span
    return (
        fact.document_id,
        span.start if span is not None else -1,
        span.end if span is not None else -1,
        fact.fact_id,
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


def _producer_signature(
    fact: CrossrefMetadataFact,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    return (
        fact.target_kind,
        tuple(sorted(fact.target_metadata)),
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
