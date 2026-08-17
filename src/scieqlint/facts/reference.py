"""Reference and target facts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.base import FactBase

TargetPlacement = Literal["before_heading", "before_block", "standalone", "orphaned"]


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


@dataclass(frozen=True, slots=True, kw_only=True)
class CrossrefMetadataFact(FactBase):
    """Source-neutral cross-reference metadata for one output boundary."""

    source_fact_id: str
    logical_target: str
    normalized_target: str
    reference_kind: str
    source_format: str
    output_boundary: str
    display_metadata: tuple[tuple[str, str], ...] = ()
    target_span: SourceSpan | None = None


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
