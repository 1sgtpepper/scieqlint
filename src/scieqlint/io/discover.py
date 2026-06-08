"""File discovery."""

from __future__ import annotations

import glob
from collections.abc import Iterable
from pathlib import Path

SUPPORTED_SUFFIXES = {".ipynb", ".md", ".markdown", ".tex"}


def discover_files(paths: Iterable[Path | str]) -> tuple[Path, ...]:
    """Discover supported files deterministically."""
    found: set[Path] = set()
    for raw in paths:
        text = str(raw)
        matches = (
            [Path(p) for p in glob.glob(text, recursive=True)]
            if any(ch in text for ch in "*?[")
            else [Path(raw)]
        )
        for path in matches:
            if path.is_dir():
                found.update(
                    p
                    for p in path.rglob("*")
                    if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
                )
            elif path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
                found.add(path)
    return tuple(sorted(found, key=lambda p: p.as_posix()))
