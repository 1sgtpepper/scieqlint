"""Math QueryView."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.math import (
    DisplayMathFact,
    InlineMathFact,
    SuspiciousFormulaFact,
    UnknownMathFact,
)
from scieqlint.facts.snapshot import FactSnapshot


@dataclass(frozen=True, slots=True)
class MathContainerQueryView:
    snapshot: FactSnapshot

    def display_math(self) -> tuple[DisplayMathFact, ...]:
        return self.snapshot.display_math

    def inline_math(self) -> tuple[InlineMathFact, ...]:
        return self.snapshot.inline_math

    def unknown_math(self) -> tuple[UnknownMathFact, ...]:
        return self.snapshot.unknown_math

    def suspicious_formulas(self) -> tuple[SuspiciousFormulaFact, ...]:
        return self.snapshot.suspicious_formulas

    def display_with_multiple_labels(self) -> tuple[DisplayMathFact, ...]:
        return tuple(fact for fact in self.snapshot.display_math if len(fact.label_fact_ids) > 1)
