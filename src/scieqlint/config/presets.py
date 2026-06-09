"""Preset config resource loading."""

from __future__ import annotations

from importlib import resources

PRESET_PACKAGE = "scieqlint.presets"


def list_presets() -> tuple[str, ...]:
    """Return available packaged preset names in stable order."""
    return tuple(
        sorted(
            resource.name.removesuffix(".toml")
            for resource in resources.files(PRESET_PACKAGE).iterdir()
            if resource.name.endswith(".toml")
        )
    )


def read_preset_text(name: str) -> str:
    """Read a packaged preset TOML resource by name."""
    if not _is_valid_preset_name(name):
        raise ValueError(f"unknown preset: {name}")
    resource = resources.files(PRESET_PACKAGE).joinpath(f"{name}.toml")
    if not resource.is_file():
        raise ValueError(f"unknown preset: {name}")
    return resource.read_text(encoding="utf-8")


def _is_valid_preset_name(name: str) -> bool:
    return bool(name) and all(char.islower() or char.isdigit() or char == "-" for char in name)
