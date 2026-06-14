"""Stable QueryHost facade over FactSnapshot."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.query.generated import GeneratedOutputQueryView
from scieqlint.query.math import MathContainerQueryView
from scieqlint.query.portability import PortabilityQueryView
from scieqlint.query.project import ProjectGraphQueryView
from scieqlint.query.reference import ReferenceQueryView
from scieqlint.query.structure import StructureQueryView


@dataclass(frozen=True, slots=True)
class QueryHost:
    snapshot: FactSnapshot

    @property
    def structure(self) -> StructureQueryView:
        return StructureQueryView(self.snapshot)

    @property
    def references(self) -> ReferenceQueryView:
        return ReferenceQueryView(self.snapshot)

    @property
    def math(self) -> MathContainerQueryView:
        return MathContainerQueryView(self.snapshot)

    @property
    def generated(self) -> GeneratedOutputQueryView:
        return GeneratedOutputQueryView(self.snapshot)

    @property
    def project(self) -> ProjectGraphQueryView:
        return ProjectGraphQueryView(self.snapshot)

    @property
    def portability(self) -> PortabilityQueryView:
        return PortabilityQueryView(self.snapshot)
