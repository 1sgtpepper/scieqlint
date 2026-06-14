"""Project graph and membership facts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from scieqlint.facts.base import FactBase


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectMemberFact(FactBase):
    path: PurePosixPath
    project_root: PurePosixPath
    declared: bool
    discovered: bool
    explicit_input: bool = False
    static_asset: bool = False
    hidden: bool = False
    excluded: bool = False
    generated: bool = False
    normalized_path: PurePosixPath | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class HiddenExcludedFact(FactBase):
    path: PurePosixPath
    reason: str
    references_may_target: bool = False
