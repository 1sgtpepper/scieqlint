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
    identity: FileIdentity | None

    def matches_path(self, path: Path) -> bool:
        return self.path_key == _lexical_path_key(path)

    def matches_identity(self, stat_result: os.stat_result) -> bool:
        return self.identity is not None and self.identity.matches(stat_result)


def _lexical_path_key(path: Path) -> str:
    """Normalize a path lexically using the host platform's path rules."""
    return os.path.normcase(os.path.abspath(os.fspath(path)))


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
            yield stream, ConsumedInput(_lexical_path_key(path), identity)
        finally:
            stream.close()
    finally:
        if descriptor is not None:
            os.close(descriptor)
