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


@contextmanager
def open_text(path: Path, *, encoding: str) -> Generator[tuple[TextIO, FileIdentity], None, None]:
    descriptor: int | None = os.open(path, os.O_RDONLY)
    try:
        identity = FileIdentity.from_stat(os.fstat(descriptor))
        stream = os.fdopen(descriptor, "r", encoding=encoding)
        descriptor = None
        try:
            yield stream, identity
        finally:
            stream.close()
    finally:
        if descriptor is not None:
            os.close(descriptor)
