"""Notebook lowering for cell metadata and output-boundary facts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import cast

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.reference import CrossrefMetadataFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import CodeCellFact, NotebookOutputFact
from scieqlint.io.source import DocumentKind, SourceDocument

from .myst_blocks import quarto_option_prefix
from .myst_shared import normalize_label

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
_CROSSREF_DISPLAY_KEYS = frozenset({"cap", "caption", "fig-cap", "lst-cap", "tbl-cap"})
_CROSSREF_PREFIXES = {
    "eq-": "equation",
    "fig-": "figure",
    "lst-": "listing",
    "tbl-": "table",
}


class NotebookFrontend:
    """Lower notebook code cells without executing or rendering the notebook."""

    def lower(self, documents: Sequence[SourceDocument]) -> FactSnapshot:
        parts = tuple(_lower_document(document) for document in documents)
        return FactSnapshot(
            documents=tuple(document for part in parts for document in part.documents),
            code_cells=tuple(fact for part in parts for fact in part.code_cells),
            notebook_outputs=tuple(fact for part in parts for fact in part.notebook_outputs),
            crossref_metadata=tuple(fact for part in parts for fact in part.crossref_metadata),
        )


def _lower_document(document: SourceDocument) -> FactSnapshot:
    if document.kind is not DocumentKind.NOTEBOOK:
        raise ValueError("NotebookFrontend requires notebook documents")
    try:
        parsed: object = json.loads(document.text)
    except (ValueError, TypeError):
        return FactSnapshot(documents=(document,))
    if not isinstance(parsed, Mapping):
        return FactSnapshot(documents=(document,))
    notebook = cast(Mapping[str, object], parsed)
    raw_cells = notebook.get("cells")
    if not isinstance(raw_cells, list):
        return FactSnapshot(documents=(document,))

    default_language = _notebook_language(notebook.get("metadata"))
    cells: list[CodeCellFact] = []
    outputs: list[NotebookOutputFact] = []
    crossrefs: list[CrossrefMetadataFact] = []
    for cell_index, raw_cell in enumerate(cast(list[object], raw_cells)):
        if not isinstance(raw_cell, Mapping):
            continue
        cell = cast(Mapping[str, object], raw_cell)
        if cell.get("cell_type") != "code":
            continue
        cell_fact, cell_outputs = _code_cell_facts(
            document,
            cell_index,
            cell,
            default_language=default_language,
        )
        cells.append(cell_fact)
        outputs.extend(cell_outputs)
        crossrefs.extend(_crossref_facts(cell_fact, cell_outputs))
    return FactSnapshot(
        documents=(document,),
        code_cells=tuple(cells),
        notebook_outputs=tuple(outputs),
        crossref_metadata=tuple(crossrefs),
    )


def _code_cell_facts(
    document: SourceDocument,
    cell_index: int,
    cell: Mapping[str, object],
    *,
    default_language: str | None,
) -> tuple[CodeCellFact, tuple[NotebookOutputFact, ...]]:
    metadata = _mapping(cell.get("metadata"))
    source = _cell_source(cell.get("source"))
    options = _cell_options(metadata, source)
    option_map = dict(options)
    language = option_map.get("language") or default_language
    engine = option_map.get("engine") or language
    cell_id = f"{document.path.as_posix()}::notebook-cell::{cell_index}"
    cell_span = _logical_cell_span(document, cell_index)
    fact = CodeCellFact(
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
        normalized_label=(
            normalize_label(option_map["label"]) if option_map.get("label") else None
        ),
        label_span=cell_span if option_map.get("label") else None,
        language_span=cell_span if language else None,
        source_format="notebook",
        tags=_tags(metadata.get("tags")),
    )

    output_facts: list[NotebookOutputFact] = []
    raw_outputs = cell.get("outputs")
    if isinstance(raw_outputs, list):
        for output_index, raw_output in enumerate(cast(list[object], raw_outputs)):
            if not isinstance(raw_output, Mapping):
                continue
            output = cast(Mapping[str, object], raw_output)
            output_metadata = _mapping(output.get("metadata"))
            data = _mapping(output.get("data"))
            output_facts.append(
                NotebookOutputFact(
                    fact_id=f"{cell_id}::output::{output_index}",
                    document_id=document.path.as_posix(),
                    span=_logical_cell_span(document, cell_index),
                    raw=None,
                    cell_fact_id=cell_id,
                    cell_index=cell_index,
                    output_index=output_index,
                    output_type=_nonempty_string(output.get("output_type")) or "unknown",
                    mime_types=tuple(sorted(str(key) for key in data)),
                    metadata=_metadata_items(output_metadata),
                )
            )
    return fact, tuple(output_facts)


def _crossref_facts(
    cell: CodeCellFact,
    outputs: Sequence[NotebookOutputFact],
) -> tuple[CrossrefMetadataFact, ...]:
    if cell.label is None:
        return ()
    kind = _crossref_kind(cell.label)
    if kind is None:
        return ()
    options = cell.option_dict()
    display_metadata = tuple(
        sorted((key, value) for key, value in options.items() if key in _CROSSREF_DISPLAY_KEYS)
    )
    boundaries = tuple(output.fact_id for output in outputs) or (
        f"{cell.fact_id}::unrendered-output",
    )
    return tuple(
        CrossrefMetadataFact(
            fact_id=f"{boundary}::crossref-metadata",
            document_id=cell.document_id,
            span=cell.span,
            raw=cell.raw,
            source_fact_id=cell.fact_id,
            logical_target=cell.label,
            normalized_target=normalize_label(cell.label),
            reference_kind=kind,
            source_format="notebook",
            output_boundary=boundary,
            resolved_target_kind=kind,
            metadata_kind="target-definition",
            target_metadata=display_metadata,
            display_metadata=display_metadata,
            target_span=cell.span,
        )
        for boundary in boundaries
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
        if all(
            isinstance(item, (str, int, float, bool)) and not isinstance(item, Mapping)
            for item in items
        ):
            return json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    return None


def _metadata_items(metadata: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = []
    for raw_key, raw_value in sorted(metadata.items(), key=lambda item: str(item[0])):
        value = _option_value(raw_value)
        if value is not None:
            items.append((str(raw_key), value))
    return tuple(items)


def _notebook_language(metadata: object) -> str | None:
    root = _mapping(metadata)
    kernelspec = _mapping(root.get("kernelspec"))
    language_info = _mapping(root.get("language_info"))
    return _nonempty_string(kernelspec.get("language")) or _nonempty_string(
        language_info.get("name")
    )


def _crossref_kind(label: str) -> str | None:
    normalized = label.strip().lower()
    for prefix, kind in _CROSSREF_PREFIXES.items():
        if normalized.startswith(prefix):
            return kind
    return None


def _tags(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, list):
        return tuple(item for item in cast(list[object], value) if isinstance(item, str) and item)
    return ()


def _cell_source(value: object) -> str | None:
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


def _logical_cell_span(document: SourceDocument, cell_index: int) -> SourceSpan:
    return SourceSpan(
        path=document.path,
        start=0,
        end=0,
        line=1,
        col=1,
        end_line=1,
        end_col=1,
        cell=cell_index,
        cell_line=1,
    )
