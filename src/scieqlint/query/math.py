"""Math QueryView."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.math import DisplayMathFact, UnknownMathFact
from scieqlint.facts.snapshot import FactSnapshot


@dataclass(frozen=True, slots=True)
class MathContainerQueryView:
    snapshot: FactSnapshot

    def display_math(self) -> tuple[DisplayMathFact, ...]:
        return self.snapshot.display_math

    def unknown_math(self) -> tuple[UnknownMathFact, ...]:
        return self.snapshot.unknown_math
