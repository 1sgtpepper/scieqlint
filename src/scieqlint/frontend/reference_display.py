"""Resolve source reference display intent into source-neutral facts."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePosixPath

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.reference import (
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    NormalizedReferenceTarget,
    ReferenceDisplayIntent,
    ReferenceDisplayTextFact,
    TargetAnchorFact,
    TargetTypeSource,
    generic_reference_identity,
    member_target_identity,
)
from scieqlint.facts.structure import CodeCellFact
from scieqlint.io.workspace import normalize_project_path

TargetFact = TargetAnchorFact | EquationLabelFact | CodeCellFact

_TARGET_PREFIX_TYPES = (
    ("eq-", "equation"),
    ("fig-", "figure"),
    ("lst-", "listing"),
    ("tbl-", "table"),
)
_DEFAULT_PROJECT_ROOT = PurePosixPath(".")


def reference_display_text_facts(
    generic_refs: Sequence[GenericRefFact],
    equation_refs: Sequence[EquationRefFact],
    target_anchors: Sequence[TargetAnchorFact],
    equation_labels: Sequence[EquationLabelFact],
    *,
    project_root: PurePosixPath = _DEFAULT_PROJECT_ROOT,
    code_cells: Sequence[CodeCellFact] = (),
) -> tuple[ReferenceDisplayTextFact, ...]:
    """Describe display text only after visible project targets are known."""

    targets: dict[str, list[TargetFact]] = {}
    identity_targets: dict[NormalizedReferenceTarget, list[TargetFact]] = {}
    equation_targets: dict[str, list[TargetFact]] = {}

    def index_target(target: TargetFact) -> None:
        label = _target_label(target)
        _retain_resolution_candidates(targets.setdefault(label, []), target)
        identity = (
            normalize_project_path(target.document_id, project_root=project_root),
            label,
        )
        _retain_resolution_candidates(identity_targets.setdefault(identity, []), target)
        if isinstance(target, EquationLabelFact):
            _retain_resolution_candidates(equation_targets.setdefault(label, []), target)

    for anchor in target_anchors:
        if anchor.visibility == "visible" and anchor.placement != "orphaned":
            index_target(anchor)
    for label in equation_labels:
        if label.visibility == "visible":
            index_target(label)
    for cell in code_cells:
        if cell.visibility == "visible" and cell.normalized_label is not None:
            index_target(cell)

    facts: list[ReferenceDisplayTextFact] = []
    for ref in generic_refs:
        identity = generic_reference_identity(ref)
        if ref.visibility != "visible" or identity is None:
            continue
        matched = tuple(
            identity_targets.get(identity, ())
            if isinstance(identity, tuple)
            else targets.get(identity, ())
        )
        facts.append(
            _display_fact(
                ref,
                reference_kind=ref.role_kind,
                explicit_text=ref.title,
                display_text_span=ref.title_span,
                matched_targets=matched,
                typed_number=False,
                project_root=project_root,
            )
        )
    for ref in equation_refs:
        if ref.visibility != "visible":
            continue
        matched = tuple(equation_targets.get(ref.normalized_target, ()))
        facts.append(
            _display_fact(
                ref,
                reference_kind=ref.ref_kind,
                explicit_text=ref.title,
                display_text_span=ref.title_span,
                matched_targets=matched,
                typed_number=ref.ref_kind in {"eq", "numref", "tex-eqref", "tex-ref"},
                project_root=project_root,
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
    project_root: PurePosixPath,
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
    target_identity = _selected_target_identity(matched_targets, project_root=project_root)
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
        target_identity=target_identity,
        target_fact_ids=(matched_targets[0].fact_id,) if len(matched_targets) == 1 else (),
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


def _selected_target_identity(
    targets: tuple[TargetFact, ...],
    *,
    project_root: PurePosixPath,
) -> NormalizedReferenceTarget | None:
    if len(targets) != 1:
        return None
    target = targets[0]
    target_label = _target_label(target)
    return member_target_identity(
        normalize_project_path(target.document_id, project_root=project_root),
        target_label,
    )


def _explicit_code_cell_target_type(cell: CodeCellFact) -> str | None:
    options = cell.option_dict()
    if "fig-cap" in options or "fig-subcap" in options:
        return "figure"
    if "tbl-cap" in options or "tbl-subcap" in options:
        return "table"
    if "lst-cap" in options:
        return "listing"
    if any(key in options for key in ("cap", "caption")):
        return "block"
    return None


def _target_key(fact: TargetFact) -> tuple[str, int, int, str]:
    span = fact.span if isinstance(fact, CodeCellFact) else fact.label_span or fact.span
    return (
        fact.document_id,
        span.start if span is not None else -1,
        span.end if span is not None else -1,
        fact.fact_id,
    )


def _retain_resolution_candidates(bucket: list[TargetFact], target: TargetFact) -> None:
    """Retain only enough source-ordered targets to distinguish ambiguity."""

    bucket.append(target)
    bucket.sort(key=_target_key)
    del bucket[2:]


def _target_label(fact: TargetFact) -> str:
    if isinstance(fact, CodeCellFact):
        assert fact.normalized_label is not None
        return fact.normalized_label
    return fact.normalized_label


def _display_fact_key(fact: ReferenceDisplayTextFact) -> tuple[str, int, int, str]:
    span = fact.span
    return (
        fact.document_id,
        span.start if span is not None else -1,
        span.end if span is not None else -1,
        fact.fact_id,
    )
