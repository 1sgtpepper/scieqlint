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
CrossrefMetadataKind = Literal["reference-use", "target-definition"]
TargetVisibility = Literal["visible", "hidden", "excluded"]


@dataclass(frozen=True, slots=True, kw_only=True)
class TargetAnchorFact(FactBase):
    label: str
    normalized_label: str
    target_kind: str | None
    attaches_to_fact_id: str | None
    placement: TargetPlacement
    visibility: TargetVisibility = "visible"
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
    visibility: TargetVisibility = "visible"


def member_target_identity(
    normalized_path: PurePosixPath | None,
    fragment: str | None,
) -> NormalizedReferenceTarget | None:
    """Return one canonical path-plus-fragment identity when both are known."""

    if normalized_path is None or fragment is None:
        return None
    normalized_fragment = fragment.strip()
    if normalized_fragment.startswith("#"):
        normalized_fragment = normalized_fragment[1:]
    if not normalized_fragment:
        return None
    return normalized_path, normalized_fragment


def normalized_reference_target(ref: GenericRefFact) -> NormalizedReferenceTarget:
    """Return the complete normalized member-path and fragment identity."""

    identity = member_target_identity(ref.normalized_target_path, ref.target_fragment)
    assert identity is not None
    return identity


def generic_reference_identity(ref: GenericRefFact) -> ReferenceIdentity | None:
    """Return the complete identity for a supported generic reference use."""

    if ref.normalized_target_path is not None:
        return normalized_reference_target(ref)
    if ref.role_kind == "ref":
        return ref.normalized_target
    return None


def format_member_target_identity(identity: NormalizedReferenceTarget) -> str:
    """Serialize one selected member-path and label identity for diagnostics."""

    path, fragment = identity
    return f"{path.as_posix()}#{fragment}"


@dataclass(frozen=True, slots=True, kw_only=True)
class CrossrefMetadataFact(FactBase):
    """Source-neutral cross-reference metadata for one output boundary."""

    source_fact_id: str
    logical_target: str
    normalized_target: str
    source_format: str
    output_boundary: str
    normalized_target_path: PurePosixPath | None = None
    reference_role: str | None = None
    display_title: str | None = None
    resolved_target_kind: str | None = None
    target_metadata: tuple[tuple[str, str], ...] = ()
    metadata_kind: CrossrefMetadataKind = "reference-use"
    target_span: SourceSpan | None = None

    def __post_init__(self) -> None:
        """Keep metadata order out of semantic identity and reporter output."""
        object.__setattr__(self, "target_metadata", tuple(sorted(self.target_metadata)))


def crossref_target_identity(fact: CrossrefMetadataFact) -> NormalizedReferenceTarget | None:
    """Return the stable target key used by metadata grouping and diagnostics."""

    return member_target_identity(fact.normalized_target_path, fact.normalized_target)


@dataclass(frozen=True, slots=True, kw_only=True)
class EquationLabelFact(FactBase):
    label: str
    normalized_label: str
    label_syntax_kind: str
    source_block_id: str | None
    namespace: str = "equation"
    visibility: TargetVisibility = "visible"
    label_span: SourceSpan | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class EquationRefFact(FactBase):
    ref_kind: str
    target: str
    normalized_target: str
    title: str | None = None
    source_block_id: str | None = None
    visibility: TargetVisibility = "visible"
    target_span: SourceSpan | None = None
    role_span: SourceSpan | None = None
