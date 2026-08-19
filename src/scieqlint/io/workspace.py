"""Lexical project-path identity owned by WorkspaceHost."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from scieqlint.facts.project import ProjectMemberFact
from scieqlint.io.source import SourceDocument


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
    """Own project identity and membership facts for frontend callers."""

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
