"""Output-profile portability facts."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.diag.model import SourceSpan


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputPortabilityFact:
    fact_id: str
    span: SourceSpan | None
    subject_fact_id: str
    output_profile: str
    risk_kind: str
    metadata: tuple[tuple[str, str], ...] = ()
