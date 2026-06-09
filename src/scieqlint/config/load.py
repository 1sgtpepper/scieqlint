"""Configuration loading."""

from __future__ import annotations

import tomllib
from pathlib import Path, PurePosixPath
from typing import Any, cast

from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    DimensionConfig,
    DimensionMode,
    DimVector,
    IgnoreConfig,
    ReportConfig,
    ReferencesConfig,
    ScannerConfig,
    UnknownVariablePolicy,
    VarDimension,
)

_BASE_DIMENSIONS = {
    "M": 0,
    "L": 1,
    "T": 2,
    "I": 3,
    "Theta": 4,
    "N": 5,
    "J": 6,
}


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
    report_data = _table(data, "report")
    vars_data = _table(data, "vars")
    algebra_data = _table(checks_data, "algebra")
    references_data = _table(checks_data, "references")
    dimension_data = _table(checks_data, "dimension")
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
            dimension=DimensionConfig(
                mode=_dimension_mode(dimension_data, "mode", "auto"),
                unknown_variables=_unknown_variable_policy(
                    dimension_data,
                    "unknown_variables",
                    "warn",
                ),
            ),
        ),
        vars=_vars_config(vars_data),
        ignore=IgnoreConfig(files=_str_tuple(ignore_data, "files")),
        report=ReportConfig(show_suppressed=_bool(report_data, "show_suppressed", False)),
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
    value: object = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list of strings")
    items: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError(f"{key} must be a list of strings")
        items.append(item)
    return tuple(items)


def _dimension_mode(
    data: dict[str, Any],
    key: str,
    default: DimensionMode,
) -> DimensionMode:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be auto, on, or off")
    if value not in {"auto", "on", "off"}:
        raise ValueError(f"{key} must be auto, on, or off")
    return cast(DimensionMode, value)


def _unknown_variable_policy(
    data: dict[str, Any],
    key: str,
    default: UnknownVariablePolicy,
) -> UnknownVariablePolicy:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be warn or ignore")
    if value not in {"warn", "ignore"}:
        raise ValueError(f"{key} must be warn or ignore")
    return cast(UnknownVariablePolicy, value)


def _vars_config(data: dict[str, Any]) -> tuple[VarDimension, ...]:
    entries: list[VarDimension] = []
    for name, expression in sorted(data.items()):
        if not name:
            raise ValueError("[vars] keys must be non-empty strings")
        if not isinstance(expression, str):
            raise ValueError(f"[vars].{name} must be a dimension string")
        entries.append(VarDimension(name=name, dimension=_parse_dimension(expression)))
    return tuple(entries)


def _parse_dimension(expression: str) -> DimVector:
    text = expression.strip()
    exponents = [0, 0, 0, 0, 0, 0, 0]
    if text == "1":
        return _dim_vector(exponents)
    if not text:
        raise ValueError("dimension expression must not be empty")
    for factor in text.split():
        base, power = _parse_dimension_factor(factor)
        exponents[_BASE_DIMENSIONS[base]] += power
    return _dim_vector(exponents)


def _parse_dimension_factor(factor: str) -> tuple[str, int]:
    base, separator, raw_power = factor.partition("^")
    if base not in _BASE_DIMENSIONS:
        raise ValueError(f"unknown base dimension: {base}")
    if not separator:
        return base, 1
    if not raw_power:
        raise ValueError(f"dimension power is missing: {factor}")
    try:
        return base, int(raw_power)
    except ValueError as exc:
        raise ValueError(f"dimension power must be an integer: {factor}") from exc


def _dim_vector(exponents: list[int]) -> DimVector:
    return DimVector(cast(tuple[int, int, int, int, int, int, int], tuple(exponents)))
