"""Notebook code-cell metadata lowering."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.structure import CodeCellFact
from scieqlint.io.source import SourceDocument

from .myst_blocks import quarto_option_prefix

_CELL_OPTION_KEYS = frozenset(
    {
        "cap",
        "caption",
        "engine",
        "fig-cap",
        "label",
        "language",
        "lst-cap",
        "renderings",
        "tags",
        "tbl-cap",
    }
)


def code_cell_fact(
    document: SourceDocument,
    cell_index: int,
    cell: Mapping[str, object],
    *,
    default_language: str | None,
    cell_span: SourceSpan | None,
) -> CodeCellFact:
    metadata = _mapping(cell.get("metadata"))
    source = cell_source(cell.get("source"))
    options = _cell_options(metadata, source)
    option_map = dict(options)
    language = option_map.get("language") or default_language
    engine = option_map.get("engine") or language
    cell_id = f"{document.path.as_posix()}::notebook-cell::{cell_index}"
    return CodeCellFact(
        fact_id=cell_id,
        document_id=document.path.as_posix(),
        span=cell_span,
        raw=source,
        fence_fact_id=cell_id,
        directive_fact_id=None,
        language=language,
        engine=engine,
        options=options,
        label=option_map.get("label"),
        tags=_tags(metadata.get("tags")),
    )


def _cell_options(
    metadata: Mapping[str, object],
    source: str | None,
) -> tuple[tuple[str, str], ...]:
    merged: dict[str, object] = dict(metadata)
    nested = _mapping(metadata.get("quarto"))
    merged.update(nested)
    normalized: dict[str, str] = {}
    for key in _CELL_OPTION_KEYS:
        if key not in merged:
            continue
        value = _option_value(merged[key])
        if value is not None:
            normalized[key] = value
    if source is not None:
        for key, value in quarto_option_prefix(source):
            if key in _CELL_OPTION_KEYS:
                normalized[key] = value
    return tuple(sorted(normalized.items()))


def _option_value(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        items = cast(list[object], value)
        if all(isinstance(item, (str, int, float, bool)) for item in items):
            return json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    return None


def notebook_language(metadata: object) -> str | None:
    root = _mapping(metadata)
    kernelspec = _mapping(root.get("kernelspec"))
    language_info = _mapping(root.get("language_info"))
    return _nonempty_string(kernelspec.get("language")) or _nonempty_string(
        language_info.get("name")
    )


def _tags(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, list):
        return tuple(item for item in cast(list[object], value) if isinstance(item, str) and item)
    return ()


def cell_source(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        items = cast(list[object], value)
        if all(isinstance(item, str) for item in items):
            return "".join(cast(list[str], items))
    return None


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return cast(Mapping[str, object], value)


def _nonempty_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
