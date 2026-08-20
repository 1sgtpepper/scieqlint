"""Config validation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

_TABLES: dict[str, frozenset[str]] = {
    "": frozenset(
        {
            "profile",
            "project",
            "baseline",
            "scanner",
            "parser",
            "checks",
            "vars",
            "aliases",
            "ignore",
            "report",
        }
    ),
    "profile": frozenset(
        {"name", "source_kind", "conversion_stage", "output_profile", "severity"}
    ),
    "project": frozenset({"root", "order", "visibility", "code_cell_languages"}),
    "baseline": frozenset({"files"}),
    "scanner": frozenset({"markdown", "inline_math", "math_fences"}),
    "parser": frozenset({"strict_unknowns"}),
    "checks": frozenset({"algebra", "references", "dimension", "symbols"}),
    "checks.algebra": frozenset({"enabled"}),
    "checks.references": frozenset({"enabled", "missing_label_strict"}),
    "checks.dimension": frozenset({"mode", "unknown_variables"}),
    "checks.symbols": frozenset({"enabled"}),
    "ignore": frozenset({"files"}),
    "report": frozenset({"show_suppressed"}),
}


def validate_config(data: Mapping[str, Any]) -> tuple[str, ...]:
    """Return unknown-key errors for the fixed config schema."""
    errors: list[str] = []
    _unknown_keys(data, "", errors)
    for table_name in _TABLES:
        if not table_name:
            continue
        table = _nested_table(data, table_name)
        if table is not None:
            _unknown_keys(table, table_name, errors)
    return tuple(errors)


def _unknown_keys(data: Mapping[str, Any], table_name: str, errors: list[str]) -> None:
    allowed = _TABLES[table_name]
    for key in data:
        if key not in allowed:
            path = f"[{table_name}].{key}" if table_name else key
            errors.append(f"unknown config key: {path}")


def _nested_table(data: Mapping[str, Any], table_name: str) -> Mapping[str, Any] | None:
    current: Any = data
    for component in table_name.split("."):
        if not isinstance(current, Mapping):
            return None
        current = cast(Mapping[str, Any], current).get(component)
    return cast(Mapping[str, Any], current) if isinstance(current, Mapping) else None
