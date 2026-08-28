"""Notebook output-boundary and cross-reference fact lowering."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import cast

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.reference import CrossrefMetadataFact, TargetAnchorFact
from scieqlint.facts.structure import CodeCellFact, NotebookOutputFact
from scieqlint.io.source import SourceDocument
from scieqlint.io.workspace import WorkspaceHost

from .myst_shared import normalize_label

_CROSSREF_DISPLAY_KEYS = frozenset({"cap", "caption", "fig-cap", "lst-cap", "tbl-cap"})


def notebook_output_facts(
    document: SourceDocument,
    cell_index: int,
    cell: Mapping[str, object],
    *,
    cell_fact_id: str,
    output_spans: Sequence[SourceSpan | None],
) -> tuple[NotebookOutputFact, ...]:
    raw_outputs = cell.get("outputs")
    if not isinstance(raw_outputs, list):
        return ()

    facts: list[NotebookOutputFact] = []
    for output_index, raw_output in enumerate(cast(list[object], raw_outputs)):
        if not isinstance(raw_output, Mapping):
            continue
        output = cast(Mapping[str, object], raw_output)
        output_metadata = _mapping(output.get("metadata"))
        data = _mapping(output.get("data"))
        output_span = output_spans[output_index] if output_index < len(output_spans) else None
        facts.append(
            NotebookOutputFact(
                fact_id=f"{cell_fact_id}::output::{output_index}",
                document_id=document.path.as_posix(),
                span=output_span,
                raw=(
                    document.text[output_span.start : output_span.end]
                    if output_span is not None
                    else None
                ),
                cell_fact_id=cell_fact_id,
                cell_index=cell_index,
                output_index=output_index,
                output_type=_nonempty_string(output.get("output_type")) or "unknown",
                mime_types=tuple(sorted(str(key) for key in data)),
                metadata=_metadata_items(output_metadata),
            )
        )
    return tuple(facts)


def crossref_facts(
    cell: CodeCellFact,
    outputs: Sequence[NotebookOutputFact],
    *,
    workspace: WorkspaceHost,
    output_label_spans: Sequence[SourceSpan | None],
) -> tuple[CrossrefMetadataFact, ...]:
    options = cell.option_dict()
    cell_metadata = {key: value for key, value in options.items() if key in _CROSSREF_DISPLAY_KEYS}
    boundaries = tuple((output.fact_id, output) for output in outputs) or (
        (f"{cell.fact_id}::unrendered-output", None),
    )
    facts: list[CrossrefMetadataFact] = []
    for boundary, output in boundaries:
        output_options = {} if output is None else dict(output.metadata)
        label = output_options.get("label") or cell.label
        if label is None:
            continue
        kind = _crossref_target_kind(label)
        if kind is None:
            continue
        metadata = dict(cell_metadata)
        if output is not None:
            metadata.update(
                {
                    key: value
                    for key, value in output_options.items()
                    if key in _CROSSREF_DISPLAY_KEYS
                }
            )
        boundary_metadata = tuple(sorted(metadata.items()))
        label_span = (
            cell.span
            if output is None or not output_options.get("label")
            else _output_label_span(output, output_label_spans)
        )
        facts.append(
            CrossrefMetadataFact(
                fact_id=f"{boundary}::crossref-metadata",
                document_id=cell.document_id,
                span=output.span if output is not None else cell.span,
                raw=output.raw if output is not None else cell.raw,
                source_fact_id=cell.fact_id,
                logical_target=label,
                normalized_target=normalize_label(label),
                source_format="notebook",
                output_boundary=boundary,
                normalized_target_path=workspace.normalize_project_path(cell.document_id),
                resolved_target_kind=kind,
                metadata_kind="target-definition",
                target_metadata=boundary_metadata,
                target_span=label_span,
            )
        )
    return tuple(facts)


def output_target_anchors(
    cell: CodeCellFact,
    outputs: Sequence[NotebookOutputFact],
    *,
    output_label_spans: Sequence[SourceSpan | None],
) -> tuple[TargetAnchorFact, ...]:
    anchors: list[TargetAnchorFact] = []
    for output in outputs:
        label = dict(output.metadata).get("label")
        if label is None or not label.strip():
            continue
        assert output.span is not None, "notebook output facts retain source spans"
        anchors.append(
            TargetAnchorFact(
                fact_id=f"{output.fact_id}::target",
                document_id=cell.document_id,
                span=output.span,
                raw=output.raw,
                label=label,
                normalized_label=normalize_label(label),
                target_kind=_crossref_target_kind(label),
                attaches_to_fact_id=output.fact_id,
                placement="standalone",
                label_span=_output_label_span(output, output_label_spans),
            )
        )
    return tuple(anchors)


def _output_label_span(
    output: NotebookOutputFact,
    output_label_spans: Sequence[SourceSpan | None],
) -> SourceSpan:
    label_span = output_label_spans[output.output_index]
    assert label_span is not None, "labeled notebook outputs retain label spans"
    return label_span


def _crossref_target_kind(label: str) -> str | None:
    normalized = normalize_label(label).casefold()
    for prefix, kind in (
        ("eq-", "equation"),
        ("fig-", "figure"),
        ("lst-", "listing"),
        ("tbl-", "table"),
    ):
        if normalized.startswith(prefix):
            return kind
    return None


def _metadata_items(metadata: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = []
    for raw_key, raw_value in sorted(metadata.items(), key=lambda item: str(item[0])):
        value = _option_value(raw_value)
        if value is not None:
            items.append((str(raw_key), value))
    return tuple(items)


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


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return cast(Mapping[str, object], value)


def _nonempty_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
