"""Project path discovery and ordering helpers."""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from pathlib import Path

from scieqlint.config.model import Config
from scieqlint.io.discover import discover_files


def project_root(config: Config) -> Path:
    root = Path(config.project.root.as_posix())
    if root.is_absolute():
        return root
    if config.path is None:
        return Path.cwd() / root
    return Path(config.path.as_posix()).parent / root


def input_paths(
    paths: Sequence[Path | str],
    config: Config,
    root: Path,
) -> tuple[Path | str, ...]:
    if paths:
        return tuple(paths)
    if config.project.order:
        return tuple(root / pattern for pattern in config.project.order)
    return (Path("."),)


def discover_project_files(
    paths: Sequence[Path | str],
    *,
    ignore_patterns: tuple[str, ...],
    order_patterns: tuple[str, ...] = (),
    root: Path | None = None,
) -> tuple[Path, ...]:
    explicit_files: list[Path] = []
    discovered_inputs: list[Path | str] = []
    for raw in paths:
        path = Path(raw)
        text = str(raw)
        if not any(ch in text for ch in "*?[") and path.is_file():
            explicit_files.append(path)
        else:
            discovered_inputs.append(raw)

    discovered = _filter_discovered_symlinks(
        _filter_ignored(
            discover_files(discovered_inputs),
            ignore_patterns,
            root=root,
        ),
        inputs=discovered_inputs,
        root=root,
    )
    return tuple(
        sorted(
            {*explicit_files, *discovered},
            key=lambda path: _path_key(path, order_patterns, root=root),
        )
    )


def _filter_discovered_symlinks(
    paths: Sequence[Path],
    *,
    inputs: Sequence[Path | str],
    root: Path | None = None,
) -> tuple[Path, ...]:
    if root is None or not _has_project_root_discovery(inputs, root):
        return tuple(paths)
    return tuple(path for path in paths if _resolved_inside_root(path, root=root))


def _has_project_root_discovery(inputs: Sequence[Path | str], root: Path) -> bool:
    resolved_root = root.resolve()
    for raw in inputs:
        text = str(raw)
        path = Path(raw)
        if any(ch in text for ch in "*?["):
            static_prefix = _glob_static_prefix(text)
            try:
                Path(static_prefix).absolute().relative_to(resolved_root)
            except ValueError:
                continue
            return True
        try:
            path.absolute().relative_to(resolved_root)
        except ValueError:
            continue
        return True
    return False


def _glob_static_prefix(pattern: str) -> str:
    parts: list[str] = []
    for part in Path(pattern).parts:
        if any(char in part for char in "*?["):
            break
        parts.append(part)
    if not parts:
        return "."
    return str(Path(*parts))


def _resolved_inside_root(path: Path, *, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _filter_ignored(
    paths: Sequence[Path],
    patterns: tuple[str, ...],
    *,
    root: Path | None = None,
) -> tuple[Path, ...]:
    if not patterns:
        return tuple(paths)
    return tuple(path for path in paths if not _is_ignored(path, patterns, root=root))


def _is_ignored(
    path: Path,
    patterns: tuple[str, ...],
    *,
    root: Path | None = None,
) -> bool:
    rel = _project_relative_path(path, root)
    absolute = path.resolve().as_posix()
    return any(
        fnmatch.fnmatchcase(rel, pattern) or fnmatch.fnmatchcase(absolute, pattern)
        for pattern in patterns
    )


def _path_key(
    path: Path,
    order_patterns: tuple[str, ...],
    *,
    root: Path | None,
) -> tuple[int, str]:
    rel = _project_relative_path(path, root)
    absolute = path.resolve().as_posix()
    for index, pattern in enumerate(order_patterns):
        if fnmatch.fnmatchcase(rel, pattern) or fnmatch.fnmatchcase(absolute, pattern):
            return (index, path.as_posix())
    return (len(order_patterns), path.as_posix())


def _project_relative_path(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()
