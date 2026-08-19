"""Resolve source reference display intent into source-neutral facts."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.reference import (
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    ReferenceDisplayIntent,
    ReferenceDisplayTextFact,
    TargetAnchorFact,
    TargetTypeSource,
)
from scieqlint.facts.structure import CodeCellFact

TargetFact = TargetAnchorFact | EquationLabelFact | CodeCellFact

_TARGET_PREFIX_TYPES = (
    ("eq-", "equation"),
    ("fig-", "figure"),
    ("lst-", "listing"),
    ("tbl-", "table"),
)


def reference_display_text_facts(
    generic_refs: Sequence[GenericRefFact],
    equation_refs: Sequence[EquationRefFact],
    target_anchors: Sequence[TargetAnchorFact],
    equation_labels: Sequence[EquationLabelFact],
    code_cells: Sequence[CodeCellFact] = (),
) -> tuple[ReferenceDisplayTextFact, ...]:
    """Describe display text only after visible project targets are known."""

    targets: dict[str, list[TargetFact]] = defaultdict(list)
    for anchor in target_anchors:
        if anchor.placement != "orphaned":
            targets[anchor.normalized_label].append(anchor)
    for label in equation_labels:
        if label.visibility == "visible":
            targets[label.normalized_label].append(label)
    for cell in code_cells:
        if cell.normalized_label is not None:
            targets[cell.normalized_label].append(cell)

    facts: list[ReferenceDisplayTextFact] = []
    for ref in generic_refs:
        matched = tuple(sorted(targets.get(ref.normalized_target, ()), key=_target_key))
        facts.append(
            _display_fact(
                ref,
                reference_kind=ref.role_kind,
                explicit_text=ref.title,
                display_text_span=ref.title_span,
                matched_targets=matched,
                typed_number=False,
            )
        )
    for ref in equation_refs:
        matched = tuple(
            target
            for target in sorted(targets.get(ref.normalized_target, ()), key=_target_key)
            if isinstance(target, EquationLabelFact)
        )
        facts.append(
            _display_fact(
                ref,
                reference_kind=ref.ref_kind,
                explicit_text=ref.title,
                display_text_span=ref.title_span,
                matched_targets=matched,
                typed_number=ref.ref_kind in {"eq", "numref"},
            )
        )
    return tuple(sorted(facts, key=_display_fact_key))


def _display_fact(
    ref: GenericRefFact | EquationRefFact,
    *,
    reference_kind: str,
    explicit_text: str | None,
    display_text_span: SourceSpan | None,
    matched_targets: tuple[TargetFact, ...],
    typed_number: bool,
) -> ReferenceDisplayTextFact:
    target_type, target_type_source = _resolved_target_type(
        ref.normalized_target,
        matched_targets,
    )
    display_intent: ReferenceDisplayIntent
    if explicit_text is not None:
        display_intent = "explicit"
    elif typed_number:
        display_intent = "typed-number"
    else:
        display_intent = "target-default"
    return ReferenceDisplayTextFact(
        fact_id=f"{ref.fact_id}::display-text",
        document_id=ref.document_id,
        span=ref.span,
        raw=ref.raw,
        origin=ref.origin,
        confidence=ref.confidence,
        source_fact_id=ref.fact_id,
        normalized_target=ref.normalized_target,
        reference_kind=reference_kind,
        explicit_text=explicit_text,
        target_type=target_type,
        display_intent=display_intent,
        target_type_source=target_type_source,
        target_fact_ids=tuple(target.fact_id for target in matched_targets),
        display_text_span=display_text_span,
    )


def _resolved_target_type(
    normalized_target: str,
    targets: tuple[TargetFact, ...],
) -> tuple[str | None, TargetTypeSource]:
    if not targets:
        return None, "unresolved"
    if len(targets) != 1:
        return None, "ambiguous"
    target = targets[0]
    if isinstance(target, EquationLabelFact):
        return "equation", "resolved"
    if isinstance(target, TargetAnchorFact) and target.target_kind is not None:
        return target.target_kind, "resolved"
    if isinstance(target, CodeCellFact):
        explicit = _explicit_code_cell_target_type(target)
        if explicit is not None:
            return explicit, "explicit"
    lowered = normalized_target.casefold()
    for prefix, target_type in _TARGET_PREFIX_TYPES:
        if lowered.startswith(prefix):
            return target_type, "inferred"
    return None, "unresolved"


def _explicit_code_cell_target_type(cell: CodeCellFact) -> str | None:
    options = cell.option_dict()
    if "fig-cap" in options:
        return "figure"
    if "tbl-cap" in options:
        return "table"
    if "lst-cap" in options:
        return "listing"
    if any(key in options for key in ("cap", "caption")):
        return "block"
    return None


def _target_key(fact: TargetFact) -> tuple[str, int, int, str]:
    span = fact.label_span or fact.span
    return (
        fact.document_id,
        span.start if span is not None else -1,
        span.end if span is not None else -1,
        fact.fact_id,
    )


def _display_fact_key(fact: ReferenceDisplayTextFact) -> tuple[str, int, int, str]:
    span = fact.span
    return (
        fact.document_id,
        span.start if span is not None else -1,
        span.end if span is not None else -1,
        fact.fact_id,
    )
