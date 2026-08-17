"""Lexical project-path identity owned by WorkspaceHost."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from scieqlint.facts.project import ProjectMemberFact
from scieqlint.io.source import SourceDocument


@dataclass(frozen=True, slots=True)
class ProjectReferenceTarget:
    """Raw and normalized path identity for one local cross-document target."""

    raw_path: str
    resolved_raw_path: str
    normalized_path: PurePosixPath
    fragment: str | None


@dataclass(frozen=True, slots=True)
class WorkspaceHost:
    """Own project identity and membership facts for frontend callers."""

    project_root: PurePosixPath = PurePosixPath(".")

    def project_reference_target(
        self,
        source_path: PurePosixPath,
        destination: str,
    ) -> ProjectReferenceTarget | None:
        return project_reference_target(source_path, destination)

    def normalize_project_path(self, path: str | PurePosixPath) -> PurePosixPath:
        return normalize_project_path(path)

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


def project_reference_target(
    source_path: PurePosixPath,
    destination: str,
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
    if raw_path.startswith("/"):
        resolved_raw = raw_path.lstrip("/")
    else:
        parent = source_path.parent.as_posix()
        resolved_raw = raw_path if parent == "." else f"{parent}/{raw_path}"

    normalized = _normalize_project_path(resolved_raw)
    fragment = parsed.fragment or None
    return ProjectReferenceTarget(
        raw_path=raw_path,
        resolved_raw_path=resolved_raw,
        normalized_path=normalized,
        fragment=fragment,
    )


def normalize_project_path(path: str | PurePosixPath) -> PurePosixPath:
    """Normalize a project-relative POSIX path without filesystem access."""

    return _normalize_project_path(path.as_posix() if isinstance(path, PurePosixPath) else path)


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
