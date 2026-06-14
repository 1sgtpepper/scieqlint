"""Reference and target facts."""

from __future__ import annotations

from dataclasses import dataclass
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
    target_span: SourceSpan | None = None
    role_span: SourceSpan | None = None
