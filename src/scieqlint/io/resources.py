"""Package resource helpers."""

from __future__ import annotations

from importlib import resources


def read_text(package: str, name: str) -> str:
    """Read a packaged text resource."""
    return resources.files(package).joinpath(name).read_text(encoding="utf-8")
