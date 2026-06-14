"""Project graph QueryView."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath

from scieqlint.facts.project import HiddenExcludedFact, ProjectMemberFact
from scieqlint.facts.snapshot import FactSnapshot


@dataclass(frozen=True, slots=True)
class ProjectGraphQueryView:
    snapshot: FactSnapshot

    def members(self) -> tuple[ProjectMemberFact, ...]:
        return self.snapshot.project_members

    def hidden_files(self) -> tuple[HiddenExcludedFact, ...]:
        return tuple(item for item in self.snapshot.hidden_excluded if item.reason == "hidden")

    def excluded_files(self) -> tuple[HiddenExcludedFact, ...]:
        return tuple(item for item in self.snapshot.hidden_excluded if item.reason != "hidden")

    def duplicate_normalized_paths(self) -> dict[PurePosixPath, tuple[ProjectMemberFact, ...]]:
        index: dict[PurePosixPath, list[ProjectMemberFact]] = defaultdict(list)
        for member in self.snapshot.project_members:
            key = member.normalized_path or member.path
            index[key].append(member)
        return {key: tuple(value) for key, value in index.items() if len(value) > 1}
