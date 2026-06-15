"""Configuration loading."""

from __future__ import annotations

import tomllib
from pathlib import Path, PurePosixPath
from typing import Any, cast

from scieqlint.config.model import (
    AlgebraConfig,
    BaselineConfig,
    ChecksConfig,
    Config,
    DimensionConfig,
    DimensionMode,
    DimVector,
    IgnoreConfig,
    ParserConfig,
    ProjectConfig,
    ReferencesConfig,
    ReportConfig,
    ScannerConfig,
    SymbolAlias,
    SymbolsConfig,
    UnknownVariablePolicy,
    VarDimension,
)
from scieqlint.config.presets import read_preset_text

_BASE_DIMENSIONS = {
    "M": 0,
    "L": 1,
    "T": 2,
    "I": 3,
    "Theta": 4,
    "N": 5,
    "J": 6,
}


def load_config(path: Path | str | None = None, *, preset: str | None = None) -> Config:
    """Load config defaults, optional preset values, and supported config options."""
    if path is None:
        config_path = _find_default_config()
    else:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"config not found: {config_path}")
    data = _config_data(config_path, preset=preset)
    project_data = _table(data, "project")
    baseline_data = _table(data, "baseline")
    parser_data = _table(data, "parser")
    scanner_data = _table(data, "scanner")
    checks_data = _table(data, "checks")
    ignore_data = _table(data, "ignore")
    report_data = _table(data, "report")
    vars_data = _table(data, "vars")
    aliases_data = _table(data, "aliases")
    algebra_data = _table(checks_data, "algebra")
    references_data = _table(checks_data, "references")
    dimension_data = _table(checks_data, "dimension")
    symbols_data = _table(checks_data, "symbols")
    vars_config = _vars_config(vars_data)
    return Config(
        path=None if config_path is None else PurePosixPath(config_path.as_posix()),
        project=ProjectConfig(
            root=_posix_path(project_data, "root", PurePosixPath(".")),
            order=_str_tuple(project_data, "order"),
        ),
        baseline=BaselineConfig(files=_str_tuple(baseline_data, "files")),
        scanner=ScannerConfig(
            markdown=_bool(scanner_data, "markdown", True),
            inline_math=_bool(scanner_data, "inline_math", False),
            math_fences=_bool(scanner_data, "math_fences", True),
        ),
        parser=ParserConfig(
            strict_unknowns=_bool(parser_data, "strict_unknowns", False),
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
            symbols=SymbolsConfig(
                enabled=_bool(symbols_data, "enabled", False),
            ),
        ),
        vars=vars_config,
        aliases=_aliases_config(aliases_data, vars_config),
        ignore=IgnoreConfig(files=_str_tuple(ignore_data, "files")),
        report=ReportConfig(show_suppressed=_bool(report_data, "show_suppressed", False)),
    )


def _config_data(config_path: Path | None, *, preset: str | None) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if preset is not None:
        data = _merge_tables(data, tomllib.loads(read_preset_text(preset)))
    if config_path is not None:
        data = _merge_tables(data, tomllib.loads(config_path.read_text(encoding="utf-8")))
    return data


def _merge_tables(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            merged[key] = _merge_tables(
                cast(dict[str, Any], base_value),
                cast(dict[str, Any], value),
            )
        else:
            merged[key] = value
    return merged


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


def _posix_path(data: dict[str, Any], key: str, default: PurePosixPath) -> PurePosixPath:
    value: object = data.get(key, default.as_posix())
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    if not value:
        raise ValueError(f"{key} must not be empty")
    return PurePosixPath(value)


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


def _aliases_config(
    data: dict[str, Any],
    vars_config: tuple[VarDimension, ...],
) -> tuple[SymbolAlias, ...]:
    canonical_names = {entry.name for entry in vars_config}
    alias_owner: dict[str, str] = {name: name for name in canonical_names}
    entries: list[SymbolAlias] = []
    for canonical, aliases in sorted(data.items()):
        if not canonical:
            raise ValueError("[aliases] keys must be non-empty strings")
        if canonical not in canonical_names:
            raise ValueError(f"[aliases].{canonical} must reference a configured variable")
        if not isinstance(aliases, list):
            raise ValueError(f"[aliases].{canonical} must be a list of strings")
        for alias in cast(list[object], aliases):
            if not isinstance(alias, str) or not alias:
                raise ValueError(f"[aliases].{canonical} must be a list of non-empty strings")
            owner = alias_owner.get(alias)
            if owner is not None and owner != canonical:
                raise ValueError(f"alias collision: {alias} maps to both {owner} and {canonical}")
            alias_owner[alias] = canonical
            if alias != canonical:
                entries.append(SymbolAlias(canonical=canonical, alias=alias))
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
