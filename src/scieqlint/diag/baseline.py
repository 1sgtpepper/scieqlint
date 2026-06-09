"""Diagnostic baseline identities."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from scieqlint.diag.model import Diagnostic

BaselineIdentity = tuple[
    str,
    str | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    str | None,
]


def baseline_identities_from_json(text: str) -> frozenset[BaselineIdentity]:
    payload: object = json.loads(text)
    data = _mapping(payload, "baseline")
    diagnostics = data.get("diagnostics", [])
    if not isinstance(diagnostics, list):
        raise ValueError("baseline diagnostics must be a list")
    diagnostics = cast(list[object], diagnostics)
    return frozenset(_entry_identity(item) for item in diagnostics)


def apply_baseline(
    diagnostics: tuple[Diagnostic, ...],
    identities: frozenset[BaselineIdentity],
) -> tuple[Diagnostic, ...]:
    if not identities:
        return diagnostics
    return tuple(
        replace(diagnostic, suppressed=True, suppression_reason="baseline")
        if diagnostic_identity(diagnostic) in identities
        else diagnostic
        for diagnostic in diagnostics
    )


def diagnostic_identity(diagnostic: Diagnostic) -> BaselineIdentity:
    span = diagnostic.span
    signal = diagnostic.equation or diagnostic.detail or diagnostic.message
    return (
        diagnostic.code,
        None if span is None else span.path.as_posix(),
        None if span is None else span.line,
        None if span is None else span.col,
        None if span is None else span.end_line,
        None if span is None else span.end_col,
        None if span is None else span.cell,
        None if span is None else span.cell_line,
        signal,
    )


def _entry_identity(value: object) -> BaselineIdentity:
    entry = _mapping(value, "baseline diagnostic")
    return (
        _required_str(entry, "code"),
        _optional_str(entry, "path"),
        _optional_int(entry, "line", minimum=1),
        _optional_int(entry, "col", minimum=1),
        _optional_int(entry, "end_line", minimum=1),
        _optional_int(entry, "end_col", minimum=1),
        _optional_int(entry, "cell", minimum=0),
        _optional_int(entry, "cell_line", minimum=1),
        _optional_str(entry, "equation")
        or _optional_str(entry, "detail")
        or _optional_str(entry, "message"),
    )


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return cast(Mapping[str, object], value)


def _required_str(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"baseline diagnostic {key} must be a non-empty string")
    return value


def _optional_str(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"baseline diagnostic {key} must be a string or null")
    return value


def _optional_int(
    data: Mapping[str, object],
    key: str,
    *,
    minimum: int,
) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"baseline diagnostic {key} must be an integer or null")
    if value < minimum:
        raise ValueError(f"baseline diagnostic {key} must be >= {minimum}")
    return value
