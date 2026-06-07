"""Configuration loading."""

from __future__ import annotations

import tomllib
from pathlib import Path, PurePosixPath
from typing import Any, cast

from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    IgnoreConfig,
    ReferencesConfig,
    ScannerConfig,
)


def load_config(path: Path | str | None = None) -> Config:
    """Load config defaults and the supported scanner options."""
    if path is None:
        config_path = _find_default_config()
        if config_path is None:
            return Config(path=None)
    else:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"config not found: {config_path}")
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    scanner_data = _table(data, "scanner")
    checks_data = _table(data, "checks")
    ignore_data = _table(data, "ignore")
    algebra_data = _table(checks_data, "algebra")
    references_data = _table(checks_data, "references")
    return Config(
        path=PurePosixPath(config_path.as_posix()),
        scanner=ScannerConfig(
            markdown=_bool(scanner_data, "markdown", True),
            inline_math=_bool(scanner_data, "inline_math", False),
            math_fences=_bool(scanner_data, "math_fences", True),
        ),
        checks=ChecksConfig(
            algebra=AlgebraConfig(
                enabled=_bool(algebra_data, "enabled", True),
            ),
            references=ReferencesConfig(
                enabled=_bool(references_data, "enabled", True),
                missing_label_strict=_bool(references_data, "missing_label_strict", False),
            ),
        ),
        ignore=IgnoreConfig(files=_str_tuple(ignore_data, "files")),
    )


def _find_default_config() -> Path | None:
    for directory in (Path.cwd(), *Path.cwd().parents):
        candidate = directory / "scieqlint.toml"
        if candidate.is_file():
            return candidate
    return None


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"[{key}] must be a table")
    return cast(dict[str, Any], value)


def _bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false")
    return value


def _str_tuple(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    return tuple(value)
