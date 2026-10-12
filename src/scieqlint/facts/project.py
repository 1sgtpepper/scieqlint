"""Project graph and membership facts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from scieqlint.facts.base import FactBase
from scieqlint.facts.reference import TargetVisibility


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectMemberFact(FactBase):
    path: PurePosixPath
    visibility: TargetVisibility = "visible"
    normalized_path: PurePosixPath | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class HiddenExcludedFact(FactBase):
    path: PurePosixPath
    reason: str
