"""Reference and target facts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.base import FactBase

TargetPlacement = Literal["before_heading", "before_block", "standalone", "orphaned"]
NormalizedReferenceTarget = tuple[PurePosixPath, str]
ReferenceIdentity = NormalizedReferenceTarget | str


@dataclass(frozen=True, slots=True, kw_only=True)
class TargetAnchorFact(FactBase):
    label: str
    normalized_label: str
    target_kind: str | None
    attaches_to_fact_id: str | None
    placement: TargetPlacement
    label_span: SourceSpan | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GenericRefFact(FactBase):
    role_kind: str
    target: str
    normalized_target: str
    title: str | None = None
    role_span: SourceSpan | None = None
    target_span: SourceSpan | None = None
    local_or_external: str = "local"
    raw_target_path: str | None = None
    resolved_raw_target_path: str | None = None
    normalized_target_path: PurePosixPath | None = None
    target_fragment: str | None = None


def normalized_reference_target(ref: GenericRefFact) -> NormalizedReferenceTarget:
    """Return the complete normalized member-path and fragment identity."""

    assert ref.normalized_target_path is not None
    assert ref.target_fragment is not None
    fragment = ref.target_fragment.strip()
    if fragment.startswith("#"):
        fragment = fragment[1:]
    assert fragment
    return ref.normalized_target_path, fragment


def generic_reference_identity(ref: GenericRefFact) -> ReferenceIdentity | None:
    """Return the complete identity for a supported generic reference use."""

    if ref.normalized_target_path is not None:
        return normalized_reference_target(ref)
    if ref.role_kind == "ref":
        return ref.normalized_target
    return None


@dataclass(frozen=True, slots=True, kw_only=True)
class EquationLabelFact(FactBase):
    label: str
    normalized_label: str
    label_syntax_kind: str
    source_block_id: str | None
    namespace: str = "equation"
    label_span: SourceSpan | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class EquationRefFact(FactBase):
    ref_kind: str
    target: str
    normalized_target: str
    source_block_id: str | None = None
    target_span: SourceSpan | None = None
    role_span: SourceSpan | None = None
