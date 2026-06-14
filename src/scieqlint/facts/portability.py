"""Output-profile portability facts."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.base import FactBase


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputPortabilityFact(FactBase):
    subject_fact_id: str
    output_profile: str
    risk_kind: str
    metadata: tuple[tuple[str, str], ...] = ()
