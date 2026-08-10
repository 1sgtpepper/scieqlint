"""Descriptor-backed identities for files consumed by the application."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


@dataclass(frozen=True, slots=True)
class FileIdentity:
    device: int
    inode: int

    @classmethod
    def from_stat(cls, stat_result: os.stat_result) -> FileIdentity:
        return cls(device=stat_result.st_dev, inode=stat_result.st_ino)

    def matches(self, stat_result: os.stat_result) -> bool:
        return self.device == stat_result.st_dev and self.inode == stat_result.st_ino


@dataclass(frozen=True, slots=True)
class ConsumedInput:
    """The lexical input role and object identity observed during consumption."""

    path: Path
    path_key: str
    normalized_path_key: str | None
    identity: FileIdentity | None
    path_metadata_complete: bool

    def matches_path(self, path: Path) -> bool:
        if self.path_key == _lexical_path_key(path):
            return True
        normalized_path_key, metadata_complete = _normalized_path_key(path)
        return (
            metadata_complete
            and self.normalized_path_key is not None
            and self.normalized_path_key == normalized_path_key
        )

    def matches_physical_path(self, path: Path) -> bool:
        """Match a path that currently resolves to this consumed role location."""
        return os.path.normcase(os.path.realpath(self.path)) == os.path.normcase(
            os.path.realpath(path)
        )

    def matches_identity(self, stat_result: os.stat_result) -> bool:
        return self.identity is not None and self.identity.matches(stat_result)

    def matches_current_identity(self, stat_result: os.stat_result) -> bool:
        """Match the object currently reached through this consumed role path."""
        try:
            current = os.stat(self.path)
        except FileNotFoundError:
            return False
        current_identity = FileIdentity.from_stat(current)
        return current_identity.matches(stat_result)


def _lexical_path_key(path: Path) -> str:
    """Anchor a lexical path without collapsing symlink-sensitive parent segments."""
    # Path.absolute() adds the current directory but retains ``..``. Using
    # os.path.abspath() here would apply normpath() and could make an output
    # path for a different file look like the consumed caller path.
    return os.path.normcase(path.absolute().as_posix())


def _normalized_path_key(path: Path) -> tuple[str | None, bool]:
    """Normalize aliases only when no traversed component is a symlink."""
    try:
        absolute = path.absolute()
        current = Path(absolute.anchor)
        for part in absolute.parts:
            if part == absolute.anchor:
                continue
            if part == "..":
                current = current.parent
                continue
            current /= part
            if current.is_symlink():
                return None, True
        return os.path.normcase(os.path.normpath(absolute.as_posix())), True
    except OSError:
        # The file was already read successfully. Preserve that analysis, but
        # report incomplete path metadata so file output can fail closed.
        return None, False


@contextmanager
def open_text(
    path: Path,
    *,
    encoding: str,
) -> Generator[tuple[TextIO, ConsumedInput], None, None]:
    role_path = path.absolute()
    descriptor: int | None = os.open(role_path, os.O_RDONLY)
    try:
        try:
            identity = FileIdentity.from_stat(os.fstat(descriptor))
        except OSError:
            identity = None
        stream = os.fdopen(descriptor, "r", encoding=encoding)
        descriptor = None
        normalized_path_key, path_metadata_complete = _normalized_path_key(path)
        try:
            yield (
                stream,
                ConsumedInput(
                    role_path,
                    _lexical_path_key(path),
                    normalized_path_key,
                    identity,
                    path_metadata_complete,
                ),
            )
        finally:
            stream.close()
    finally:
        if descriptor is not None:
            os.close(descriptor)
