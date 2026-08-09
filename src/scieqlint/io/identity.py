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

    path_key: str
    normalized_path_key: str | None
    identity: FileIdentity | None

    def matches_path(self, path: Path) -> bool:
        if self.path_key == _lexical_path_key(path):
            return True
        return (
            self.normalized_path_key is not None
            and self.normalized_path_key == _normalized_path_key(path)
        )

    def matches_identity(self, stat_result: os.stat_result) -> bool:
        return self.identity is not None and self.identity.matches(stat_result)


def _lexical_path_key(path: Path) -> str:
    """Anchor a lexical path without collapsing symlink-sensitive parent segments."""
    # Path.absolute() adds the current directory but retains ``..``. Using
    # os.path.abspath() here would apply normpath() and could make an output
    # path for a different file look like the consumed caller path.
    return os.path.normcase(path.absolute().as_posix())


def _normalized_path_key(path: Path) -> str | None:
    """Normalize aliases only when no traversed component is a symlink."""
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
            return None
    return os.path.normcase(os.path.normpath(absolute.as_posix()))


@contextmanager
def open_text(
    path: Path,
    *,
    encoding: str,
) -> Generator[tuple[TextIO, ConsumedInput], None, None]:
    descriptor: int | None = os.open(path, os.O_RDONLY)
    try:
        try:
            identity = FileIdentity.from_stat(os.fstat(descriptor))
        except OSError:
            identity = None
        stream = os.fdopen(descriptor, "r", encoding=encoding)
        descriptor = None
        try:
            yield stream, ConsumedInput(
                _lexical_path_key(path),
                _normalized_path_key(path),
                identity,
            )
        finally:
            stream.close()
    finally:
        if descriptor is not None:
            os.close(descriptor)
