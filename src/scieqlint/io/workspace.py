"""Lexical project-path identity owned by WorkspaceHost."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

from scieqlint.facts.project import HiddenExcludedFact, ProjectMemberFact
from scieqlint.facts.reference import TargetVisibility
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.io.source import SourceDocument

WorkspaceVisibility = Literal["visible", "hidden", "excluded"]


_DEFAULT_PROJECT_ROOT = PurePosixPath(".")


@dataclass(frozen=True, slots=True)
class ProjectReferenceTarget:
    """Raw and normalized path identity for one local cross-document target."""

    raw_path: str
    resolved_raw_path: str
    normalized_path: PurePosixPath
    fragment: str | None


@dataclass(frozen=True, slots=True)
class WorkspaceHost:
    """Own project identity, membership, and render visibility projection."""

    project_root: PurePosixPath = PurePosixPath(".")

    def project_reference_target(
        self,
        source_path: PurePosixPath,
        destination: str,
    ) -> ProjectReferenceTarget | None:
        return project_reference_target(source_path, destination, project_root=self.project_root)

    def normalize_project_path(self, path: str | PurePosixPath) -> PurePosixPath:
        return normalize_project_path(path, project_root=self.project_root)

    def project_members(
        self,
        documents: Sequence[SourceDocument],
    ) -> tuple[ProjectMemberFact, ...]:
        """Record caller-provided documents using one canonical path identity."""

        return tuple(
            ProjectMemberFact(
                fact_id=f"{document.path.as_posix()}::project-member",
                document_id=document.path.as_posix(),
                span=None,
                path=document.path,
                project_root=self.project_root,
                declared=True,
                discovered=True,
                explicit_input=True,
                normalized_path=self.normalize_project_path(document.path),
            )
            for document in documents
        )

    def project_facts(
        self,
        documents: Sequence[SourceDocument],
        visibility: Mapping[str, WorkspaceVisibility] | None = None,
    ) -> tuple[tuple[ProjectMemberFact, ...], tuple[HiddenExcludedFact, ...]]:
        """Project caller-owned visibility into immutable member facts.

        The workspace does not infer visibility from filenames or target labels.
        Callers provide a path-keyed membership projection; omitted documents
        remain visible, matching the existing single-document API contract.
        """

        supplied: dict[str, WorkspaceVisibility] = {}
        for path, state in (visibility or {}).items():
            if state not in {"visible", "hidden", "excluded"}:
                raise ValueError(f"unsupported workspace visibility: {state}")
            supplied[str(path)] = state
        members: list[ProjectMemberFact] = []
        hidden_excluded: list[HiddenExcludedFact] = []
        for document in documents:
            path = document.path
            document_id = path.as_posix()
            state = supplied.get(document_id, "visible")
            member = ProjectMemberFact(
                fact_id=f"{document_id}::project-member",
                document_id=document_id,
                span=None,
                path=path,
                project_root=self.project_root,
                declared=True,
                discovered=True,
                explicit_input=True,
                hidden=state == "hidden",
                excluded=state == "excluded",
                normalized_path=self.normalize_project_path(path),
            )
            members.append(member)
            if state != "visible":
                hidden_excluded.append(
                    HiddenExcludedFact(
                        fact_id=f"{document_id}::workspace::{state}",
                        document_id=document_id,
                        span=None,
                        raw=None,
                        path=path,
                        reason=state,
                        references_may_target=True,
                    )
                )
        return tuple(members), tuple(hidden_excluded)

    def apply_visibility(
        self,
        snapshot: FactSnapshot,
        visibility: Mapping[str, WorkspaceVisibility] | None = None,
    ) -> FactSnapshot:
        """Apply caller-owned workspace state to labels and project facts."""

        members, hidden_excluded = self.project_facts(snapshot.documents, visibility)
        states = {member.document_id: _member_visibility(member) for member in members}
        labels = tuple(
            replace(label, visibility=states.get(label.document_id, "visible"))
            for label in snapshot.equation_labels
        )
        return replace(
            snapshot,
            equation_labels=labels,
            project_members=members,
            hidden_excluded=hidden_excluded,
        )


def project_reference_target(
    source_path: PurePosixPath,
    destination: str,
    *,
    project_root: PurePosixPath = _DEFAULT_PROJECT_ROOT,
) -> ProjectReferenceTarget | None:
    """Return lexical project identity for a local path-bearing destination.

    URL schemes, network locations, and fragment-only links are not project paths.
    Normalization is purely lexical: this helper never reads or resolves the
    filesystem.
    """

    parsed = urlsplit(destination)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None

    raw_path = parsed.path
    normalized_root = _normalize_project_path(project_root.as_posix())
    if raw_path.startswith("/"):
        root_prefix = "" if normalized_root == PurePosixPath(".") else f"{normalized_root}/"
        resolved_raw = f"{root_prefix}{raw_path.lstrip('/')}"
    else:
        parent = source_path.parent.as_posix()
        resolved_raw = raw_path if parent == "." else f"{parent}/{raw_path}"

    normalized = _relative_to_project_root(
        _normalize_project_path(resolved_raw),
        normalized_root,
    )
    fragment = parsed.fragment or None
    return ProjectReferenceTarget(
        raw_path=raw_path,
        resolved_raw_path=resolved_raw,
        normalized_path=normalized,
        fragment=fragment,
    )


def normalize_project_path(
    path: str | PurePosixPath,
    *,
    project_root: PurePosixPath = _DEFAULT_PROJECT_ROOT,
) -> PurePosixPath:
    """Normalize a project-relative POSIX path without filesystem access."""

    normalized = _normalize_project_path(
        path.as_posix() if isinstance(path, PurePosixPath) else path
    )
    return _relative_to_project_root(
        normalized,
        _normalize_project_path(project_root.as_posix()),
    )


def _normalize_project_path(path: str) -> PurePosixPath:
    parts: list[str] = []
    for part in path.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            else:
                parts.append(part)
            continue
        parts.append(part)
    return PurePosixPath(*parts) if parts else PurePosixPath(".")


def _relative_to_project_root(
    path: PurePosixPath,
    project_root: PurePosixPath,
) -> PurePosixPath:
    if project_root == PurePosixPath("."):
        return path
    path_parts = path.parts
    root_parts = project_root.parts
    common = 0
    for path_part, root_part in zip(path_parts, root_parts, strict=False):
        if path_part != root_part:
            break
        common += 1
    if common == len(root_parts):
        relative_parts = path_parts[common:]
    else:
        relative_parts = ("..",) * (len(root_parts) - common) + path_parts[common:]
    return PurePosixPath(*relative_parts) if relative_parts else PurePosixPath(".")


def _member_visibility(member: ProjectMemberFact) -> TargetVisibility:
    if member.excluded:
        return "excluded"
    if member.hidden:
        return "hidden"
    return "visible"
