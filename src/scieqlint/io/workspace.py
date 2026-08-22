"""Lexical project-path identity owned by WorkspaceHost."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import PurePath, PurePosixPath, PureWindowsPath
from urllib.parse import unquote_to_bytes, urlsplit

from scieqlint.facts.project import HiddenExcludedFact, ProjectMemberFact
from scieqlint.facts.reference import TargetVisibility
from scieqlint.facts.snapshot import FactSnapshot
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

    def project_facts(
        self,
        documents: Sequence[SourceDocument],
        visibility: (
            Mapping[str, TargetVisibility] | Sequence[tuple[str, TargetVisibility]] | None
        ) = None,
    ) -> tuple[tuple[ProjectMemberFact, ...], tuple[HiddenExcludedFact, ...]]:
        """Project configured visibility into immutable member facts.

        The workspace does not infer visibility from filenames or target labels.
        The application provides project-relative path keys; omitted documents
        remain visible, matching the existing single-document API contract.
        """

        seen_document_paths: set[PurePosixPath] = set()
        duplicate_document_paths: set[PurePosixPath] = set()
        raw_paths_by_normalized: dict[PurePosixPath, set[PurePosixPath]] = {}
        visibility_paths_by_normalized: dict[PurePosixPath, set[PurePosixPath]] = {}
        for document in documents:
            if document.path in seen_document_paths:
                duplicate_document_paths.add(document.path)
            else:
                seen_document_paths.add(document.path)
            raw_paths_by_normalized.setdefault(
                self.normalize_project_path(document.path),
                set(),
            ).add(document.path)
            visibility_paths_by_normalized.setdefault(
                self._visibility_path(document.path),
                set(),
            ).add(document.path)
        if duplicate_document_paths:
            paths = ", ".join(
                path.as_posix()
                for path in sorted(duplicate_document_paths, key=lambda path: path.as_posix())
            )
            raise ValueError(f"duplicate document path(s): {paths}")
        duplicate_normalized_paths = tuple(
            sorted(
                (
                    normalized_path,
                    raw_paths,
                )
                for normalized_path, raw_paths in raw_paths_by_normalized.items()
                if len(raw_paths) > 1
            )
        )
        if duplicate_normalized_paths:
            details = "; ".join(
                f"{normalized_path.as_posix()} "
                f"({', '.join(sorted(path.as_posix() for path in raw_paths))})"
                for normalized_path, raw_paths in duplicate_normalized_paths
            )
            raise ValueError(f"duplicate normalized document path(s): {details}")

        supplied: dict[PurePosixPath, TargetVisibility] = {}
        visibility_entries = tuple(
            visibility.items() if isinstance(visibility, Mapping) else visibility or ()
        )
        duplicate_visibility_paths = tuple(
            sorted(
                (
                    normalized_path,
                    raw_paths,
                )
                for normalized_path, raw_paths in visibility_paths_by_normalized.items()
                if len(raw_paths) > 1
            )
        )
        if visibility_entries and duplicate_visibility_paths:
            details = "; ".join(
                f"{normalized_path.as_posix()} "
                f"({', '.join(sorted(path.as_posix() for path in raw_paths))})"
                for normalized_path, raw_paths in duplicate_visibility_paths
            )
            raise ValueError(f"duplicate project visibility document path(s): {details}")
        for path, state in visibility_entries:
            if state not in {"visible", "hidden", "excluded"}:
                raise ValueError(f"unsupported workspace visibility: {state}")
            normalized_path = self._visibility_path(path)
            previous = supplied.get(normalized_path)
            if previous is not None and previous != state:
                raise ValueError(
                    f"conflicting project visibility entries for {normalized_path.as_posix()}"
                )
            supplied[normalized_path] = state

        document_paths = {self._visibility_path(document.path) for document in documents}
        unknown_paths = sorted(path.as_posix() for path in supplied if path not in document_paths)
        if unknown_paths:
            raise ValueError("unknown project visibility member(s): " + ", ".join(unknown_paths))

        members: list[ProjectMemberFact] = []
        hidden_excluded: list[HiddenExcludedFact] = []
        for document in documents:
            path = document.path
            document_id = path.as_posix()
            state = supplied.get(self._visibility_path(path), "visible")
            member = ProjectMemberFact(
                fact_id=f"{document_id}::project-member",
                document_id=document_id,
                span=None,
                path=path,
                project_root=self.project_root,
                declared=True,
                discovered=True,
                explicit_input=True,
                visibility=state,
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

    def project_visibility(
        self,
        documents: Sequence[SourceDocument],
        visibility: (
            Mapping[str, TargetVisibility] | Sequence[tuple[str, TargetVisibility]] | None
        ) = None,
    ) -> tuple[tuple[str, TargetVisibility], ...]:
        """Keep visibility entries whose project members are in ``documents``.

        Profile snapshots may contain only a subset of the documents checked by the
        application. Filtering is owned here so configured project-relative keys and
        caller-provided root spellings use the same identity as ``project_facts``.
        """

        visibility_entries = (
            visibility.items() if isinstance(visibility, Mapping) else visibility or ()
        )
        document_paths = {self._visibility_path(document.path) for document in documents}
        return tuple(
            (path, state)
            for path, state in visibility_entries
            if self._visibility_path(path) in document_paths
        )

    def apply_visibility(
        self,
        snapshot: FactSnapshot,
        visibility: (
            Mapping[str, TargetVisibility] | Sequence[tuple[str, TargetVisibility]] | None
        ) = None,
    ) -> FactSnapshot:
        """Apply configured project state before reference resolution."""

        members, hidden_excluded = self.project_facts(snapshot.documents, visibility)
        states = {member.document_id: member.visibility for member in members}
        anchors = tuple(
            replace(anchor, visibility=states.get(anchor.document_id, "visible"))
            for anchor in snapshot.target_anchors
        )
        generic_refs = tuple(
            replace(ref, visibility=states.get(ref.document_id, "visible"))
            for ref in snapshot.generic_refs
        )
        labels = tuple(
            replace(label, visibility=states.get(label.document_id, "visible"))
            for label in snapshot.equation_labels
        )
        refs = tuple(
            replace(ref, visibility=states.get(ref.document_id, "visible"))
            for ref in snapshot.equation_refs
        )
        code_cells = tuple(
            replace(cell, visibility=states.get(cell.document_id, "visible"))
            for cell in snapshot.code_cells
        )
        return replace(
            snapshot,
            target_anchors=anchors,
            generic_refs=generic_refs,
            equation_labels=labels,
            equation_refs=refs,
            code_cells=code_cells,
            project_members=members,
            hidden_excluded=hidden_excluded,
        )

    def _visibility_path(self, path: str | PurePath) -> PurePosixPath:
        """Normalize project-relative visibility keys and document path spellings."""

        raw_path = _normalize_project_path(_path_as_posix(path))
        normalized_root = _normalize_project_path(_path_as_posix(self.project_root))
        if normalized_root == PurePosixPath("."):
            return raw_path
        windows_style = _is_windows_style_path(path) or _is_windows_style_path(self.project_root)
        raw_prefix = raw_path.parts[: len(normalized_root.parts)]
        root_parts = normalized_root.parts
        has_root_prefix = (
            tuple(part.casefold() for part in raw_prefix)
            == tuple(part.casefold() for part in root_parts)
            if windows_style
            else raw_prefix == root_parts
        )
        if not has_root_prefix:
            raw_path = PurePosixPath(*normalized_root.parts, *raw_path.parts)
        return self.normalize_project_path(raw_path)


def project_reference_target(
    source_path: PurePosixPath,
    destination: str,
    *,
    project_root: PurePosixPath = _DEFAULT_PROJECT_ROOT,
) -> ProjectReferenceTarget | None:
    """Return lexical project identity for a local path-bearing destination.

    URL schemes, network locations, and fragment-only links are not project paths.
    Native Windows drive and UNC spellings are accepted as local paths, while
    protocol-relative URLs remain external. URL path and fragment components are
    decoded as UTF-8 before lexical normalization. A target that escapes the
    configured project root is treated as external. This helper never reads or
    resolves the filesystem.
    """

    parsed = _parse_project_destination(destination)
    if parsed is None:
        return None

    raw_path, decoded_raw_path, fragment = parsed
    windows_style = (
        _is_windows_style_path(source_path)
        or _is_windows_style_path(destination)
        or _is_windows_style_path(project_root)
        or _is_windows_style_path(decoded_raw_path)
    )
    native_absolute = _is_native_absolute(decoded_raw_path)
    root_relative = decoded_raw_path.startswith("/") or _is_windows_root_relative(decoded_raw_path)
    normalized_root = _normalize_project_path(_path_as_posix(project_root))
    if native_absolute:
        resolved_raw = raw_path
        path_for_normalization = decoded_raw_path
    elif root_relative:
        root_prefix = "" if normalized_root == PurePosixPath(".") else f"{normalized_root}/"
        raw_root_path = raw_path.lstrip("/\\")
        decoded_root_path = decoded_raw_path.lstrip("/\\")
        resolved_raw = f"{root_prefix}{raw_root_path}"
        path_for_normalization = f"{root_prefix}{decoded_root_path}"
    else:
        parent = PurePosixPath(_path_as_posix(source_path)).parent.as_posix()
        resolved_raw = raw_path if parent == "." else f"{parent}/{raw_path}"
        path_for_normalization = (
            decoded_raw_path if parent == "." else f"{parent}/{decoded_raw_path}"
        )

    normalized = _relative_to_project_root(
        _normalize_project_path(path_for_normalization),
        normalized_root,
        case_insensitive=windows_style,
    )
    if _escapes_project_root(normalized):
        return None
    return ProjectReferenceTarget(
        raw_path=raw_path,
        resolved_raw_path=resolved_raw,
        normalized_path=normalized,
        fragment=fragment,
    )


def normalize_project_path(
    path: str | PurePath,
    *,
    project_root: PurePosixPath = _DEFAULT_PROJECT_ROOT,
) -> PurePosixPath:
    """Normalize a project-relative POSIX path without filesystem access."""

    normalized = _normalize_project_path(_path_as_posix(path))
    return _relative_to_project_root(
        normalized,
        _normalize_project_path(_path_as_posix(project_root)),
        case_insensitive=_is_windows_style_path(path) or _is_windows_style_path(project_root),
    )


def _normalize_project_path(path: str) -> PurePosixPath:
    parts: list[str] = []
    for part in path.replace("\\", "/").split("/"):
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


def _parse_project_destination(
    destination: str,
) -> tuple[str, str, str | None] | None:
    """Parse one local destination without allowing malformed URLs to escape."""

    raw_path = destination.split("#", 1)[0].split("?", 1)[0]
    if not raw_path:
        return None
    decoded_raw_path = _decode_url_component(raw_path)
    if decoded_raw_path is None:
        return None
    if decoded_raw_path.startswith("//") and not decoded_raw_path.startswith("\\\\"):
        # Percent-encoded protocol-relative URLs must remain external too; do
        # not let decoding turn an external destination into a root-relative one.
        return None
    candidate = destination.replace("\\", "/")
    if _looks_like_windows_path(destination):
        # urlsplit treats a drive letter as a URL scheme. Prefixing the spelling
        # keeps the drive path local while retaining its lexical components.
        candidate = f"./{candidate}"
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        # Invalid bracketed hosts and other malformed URL forms are unsupported
        # destinations, not fatal analysis errors.
        return None
    if parsed.scheme and not _is_native_absolute(decoded_raw_path):
        return None
    if parsed.netloc or not parsed.path:
        return None
    fragment = _decode_url_component(parsed.fragment)
    if parsed.fragment and (fragment is None or not _has_nonempty_fragment(fragment)):
        return None
    return raw_path, decoded_raw_path, fragment or None


def decode_project_fragment(fragment: str) -> str | None:
    """Decode one fragment-only target, rejecting empty or malformed values."""

    decoded = _decode_url_component(fragment)
    return decoded if decoded is not None and _has_nonempty_fragment(decoded) else None


def _decode_url_component(value: str) -> str | None:
    try:
        return unquote_to_bytes(value).decode("utf-8")
    except UnicodeError:
        return None


def _looks_like_windows_path(path: str) -> bool:
    return (len(path) >= 2 and path[0].isalpha() and path[1] == ":") or path.startswith("\\\\")


def _is_native_absolute(path: str) -> bool:
    return _is_windows_drive_absolute(path) or path.startswith("\\\\")


def _is_windows_root_relative(path: str) -> bool:
    return path.startswith("\\") and not path.startswith("\\\\")


def _is_windows_style_path(path: str | PurePath) -> bool:
    return isinstance(path, PureWindowsPath) or _looks_like_windows_path(str(path))


def _has_nonempty_fragment(fragment: str) -> bool:
    candidate = fragment.strip()
    if candidate.startswith("#"):
        candidate = candidate[1:].strip()
    return bool(candidate)


def _is_windows_drive_absolute(path: str) -> bool:
    return len(path) >= 3 and path[0].isalpha() and path[1] == ":" and path[2] in "/\\"


def _escapes_project_root(path: PurePosixPath) -> bool:
    return bool(path.parts) and path.parts[0] == ".."


def _path_as_posix(path: str | PurePath) -> str:
    return (path if isinstance(path, str) else path.as_posix()).replace("\\", "/")


def _relative_to_project_root(
    path: PurePosixPath,
    project_root: PurePosixPath,
    *,
    case_insensitive: bool = False,
) -> PurePosixPath:
    if project_root == PurePosixPath("."):
        return _casefold_path(path) if case_insensitive else path
    path_parts = path.parts
    root_parts = project_root.parts
    common = 0
    for path_part, root_part in zip(path_parts, root_parts, strict=False):
        if (
            path_part.casefold() != root_part.casefold()
            if case_insensitive
            else path_part != root_part
        ):
            break
        common += 1
    if common == len(root_parts):
        relative_parts = path_parts[common:]
    else:
        relative_parts = ("..",) * (len(root_parts) - common) + path_parts[common:]
    if case_insensitive:
        relative_parts = tuple(part.casefold() for part in relative_parts)
    return PurePosixPath(*relative_parts) if relative_parts else PurePosixPath(".")


def _casefold_path(path: PurePosixPath) -> PurePosixPath:
    parts = tuple(part.casefold() for part in path.parts)
    return PurePosixPath(*parts) if parts else PurePosixPath(".")
