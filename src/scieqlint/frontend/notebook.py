"""Notebook lowering for cell metadata and output-boundary facts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast, overload

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.reference import (
    CrossrefMetadataFact,
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
)
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import CodeCellFact, NotebookOutputFact
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.io.workspace import WorkspaceHost
from scieqlint.scan.notebook import NotebookInput, NotebookScanner

from .myst import MySTFrontend
from .myst_blocks import quarto_option_prefix
from .myst_shared import crossref_target_kind, normalize_label

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


class NotebookFrontend:
    """Lower notebook metadata and Markdown references without execution."""

    def __init__(self, *, workspace: WorkspaceHost | None = None) -> None:
        self.workspace = workspace or WorkspaceHost()

    def lower(
        self,
        documents: Sequence[SourceDocument],
        *,
        parsed: Mapping[str, NotebookInput] | None = None,
    ) -> FactSnapshot:
        parts = tuple(
            _lower_document(
                document,
                parsed=None if parsed is None else parsed.get(document.path.as_posix()),
                workspace=self.workspace,
            )
            for document in documents
        )
        return FactSnapshot(
            documents=tuple(document for part in parts for document in part.documents),
            code_cells=tuple(fact for part in parts for fact in part.code_cells),
            notebook_outputs=tuple(fact for part in parts for fact in part.notebook_outputs),
            generic_refs=tuple(fact for part in parts for fact in part.generic_refs),
            equation_labels=tuple(fact for part in parts for fact in part.equation_labels),
            equation_refs=tuple(fact for part in parts for fact in part.equation_refs),
            crossref_metadata=tuple(fact for part in parts for fact in part.crossref_metadata),
        )


def _lower_document(
    document: SourceDocument,
    *,
    parsed: NotebookInput | None,
    workspace: WorkspaceHost,
) -> FactSnapshot:
    if document.kind is not DocumentKind.NOTEBOOK:
        raise ValueError("NotebookFrontend requires notebook documents")
    notebook_input = parsed or NotebookScanner().parse(document)
    if not notebook_input.valid:
        if parsed is not None:
            return FactSnapshot(documents=(document,))
        detail = notebook_input.diagnostics[0].detail if notebook_input.diagnostics else None
        raise ValueError(f"invalid notebook input: {detail or 'notebook cannot be lowered'}")
    assert notebook_input.root is not None
    notebook = notebook_input.root

    default_language = _notebook_language(notebook.get("metadata"))
    cells: list[CodeCellFact] = []
    outputs: list[NotebookOutputFact] = []
    generic_refs: list[GenericRefFact] = []
    equation_labels: list[EquationLabelFact] = []
    equation_refs: list[EquationRefFact] = []
    crossrefs: list[CrossrefMetadataFact] = []
    for cell_index, raw_cell in enumerate(notebook_input.cells):
        if not isinstance(raw_cell, Mapping):
            continue
        cell = cast(Mapping[str, object], raw_cell)
        if cell.get("cell_type") == "markdown":
            source = _cell_source(cell.get("source"))
            if source is not None:
                markdown_refs, markdown_labels, markdown_equation_refs = _markdown_cell_references(
                    document,
                    cell_index,
                    source,
                    workspace=workspace,
                )
                generic_refs.extend(markdown_refs)
                equation_labels.extend(markdown_labels)
                equation_refs.extend(markdown_equation_refs)
            continue
        if cell.get("cell_type") != "code":
            continue
        source = _cell_source(cell.get("source"))
        cell_fact, cell_outputs = _code_cell_facts(
            document,
            cell_index,
            cell,
            default_language=default_language,
            cell_span=(
                _logical_cell_span(document, cell_index, source)
                if source is not None
                else notebook_input.cell_spans[cell_index]
                if cell_index < len(notebook_input.cell_spans)
                else None
            ),
            output_spans=(
                notebook_input.output_spans[cell_index]
                if cell_index < len(notebook_input.output_spans)
                else ()
            ),
        )
        cells.append(cell_fact)
        outputs.extend(cell_outputs)
        crossrefs.extend(_crossref_facts(cell_fact, cell_outputs))
    return FactSnapshot(
        documents=(document,),
        code_cells=tuple(cells),
        notebook_outputs=tuple(outputs),
        generic_refs=tuple(generic_refs),
        equation_labels=tuple(equation_labels),
        equation_refs=tuple(equation_refs),
        crossref_metadata=tuple(crossrefs),
    )


def _markdown_cell_references(
    document: SourceDocument,
    cell_index: int,
    source: str,
    *,
    workspace: WorkspaceHost,
) -> tuple[
    tuple[GenericRefFact, ...],
    tuple[EquationLabelFact, ...],
    tuple[EquationRefFact, ...],
]:
    cell_document = SourceDocument.from_text(document.path, source, DocumentKind.MARKDOWN)
    snapshot = MySTFrontend(workspace=workspace).lower((cell_document,))
    return (
        tuple(_with_notebook_cell(fact, document, cell_index) for fact in snapshot.generic_refs),
        tuple(
            _with_notebook_cell_label(fact, document, cell_index)
            for fact in snapshot.equation_labels
        ),
        tuple(_with_notebook_cell(fact, document, cell_index) for fact in snapshot.equation_refs),
    )


@overload
def _with_notebook_cell(
    fact: GenericRefFact,
    document: SourceDocument,
    cell_index: int,
) -> GenericRefFact: ...


@overload
def _with_notebook_cell(
    fact: EquationRefFact,
    document: SourceDocument,
    cell_index: int,
) -> EquationRefFact: ...


def _with_notebook_cell(
    fact: GenericRefFact | EquationRefFact,
    document: SourceDocument,
    cell_index: int,
) -> GenericRefFact | EquationRefFact:
    prefix = f"{document.path.as_posix()}::notebook-cell::{cell_index}::"
    if isinstance(fact, GenericRefFact):
        return replace(
            fact,
            fact_id=f"{prefix}{fact.fact_id}",
            document_id=document.path.as_posix(),
            span=_with_notebook_cell_span(fact.span, cell_index),
            title_span=_with_notebook_cell_span(fact.title_span, cell_index),
            role_span=_with_notebook_cell_span(fact.role_span, cell_index),
            target_span=_with_notebook_cell_span(fact.target_span, cell_index),
        )
    return replace(
        fact,
        fact_id=f"{prefix}{fact.fact_id}",
        document_id=document.path.as_posix(),
        span=_with_notebook_cell_span(fact.span, cell_index),
        title_span=_with_notebook_cell_span(fact.title_span, cell_index),
        role_span=_with_notebook_cell_span(fact.role_span, cell_index),
        target_span=_with_notebook_cell_span(fact.target_span, cell_index),
    )


def _with_notebook_cell_span(span: SourceSpan | None, cell_index: int) -> SourceSpan | None:
    if span is None:
        return None
    return replace(span, cell=cell_index, cell_line=span.line)


def _with_notebook_cell_label(
    fact: EquationLabelFact,
    document: SourceDocument,
    cell_index: int,
) -> EquationLabelFact:
    prefix = f"{document.path.as_posix()}::notebook-cell::{cell_index}::"
    source_block_id = None if fact.source_block_id is None else f"{prefix}{fact.source_block_id}"
    return replace(
        fact,
        fact_id=f"{prefix}{fact.fact_id}",
        document_id=document.path.as_posix(),
        span=_with_notebook_cell_span(fact.span, cell_index),
        label_span=_with_notebook_cell_span(fact.label_span, cell_index),
        source_block_id=source_block_id,
    )


def _code_cell_facts(
    document: SourceDocument,
    cell_index: int,
    cell: Mapping[str, object],
    *,
    default_language: str | None,
    cell_span: SourceSpan | None,
    output_spans: Sequence[SourceSpan | None],
) -> tuple[CodeCellFact, tuple[NotebookOutputFact, ...]]:
    metadata = _mapping(cell.get("metadata"))
    source = _cell_source(cell.get("source"))
    options = _cell_options(metadata, source)
    option_map = dict(options)
    language = option_map.get("language") or default_language
    engine = option_map.get("engine") or language
    label = option_map.get("label") or None
    cell_id = f"{document.path.as_posix()}::notebook-cell::{cell_index}"
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
        label=label,
        normalized_label=normalize_label(label) if label is not None else None,
        label_span=cell_span if label is not None else None,
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
            output_span = output_spans[output_index] if output_index < len(output_spans) else None
            output_facts.append(
                NotebookOutputFact(
                    fact_id=f"{cell_id}::output::{output_index}",
                    document_id=document.path.as_posix(),
                    span=output_span,
                    raw=(
                        document.text[output_span.start : output_span.end]
                        if output_span is not None
                        else None
                    ),
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
    kind = crossref_target_kind(cell.label)
    if kind is None:
        return ()
    options = cell.option_dict()
    cell_metadata = {key: value for key, value in options.items() if key in _CROSSREF_DISPLAY_KEYS}
    boundaries = tuple((output.fact_id, output) for output in outputs) or (
        (f"{cell.fact_id}::unrendered-output", None),
    )
    return tuple(
        CrossrefMetadataFact(
            fact_id=f"{boundary}::crossref-metadata",
            document_id=cell.document_id,
            span=output.span if output is not None else cell.span,
            raw=output.raw if output is not None else cell.raw,
            source_fact_id=cell.fact_id,
            logical_target=cell.label,
            normalized_target=normalize_label(cell.label),
            target_kind=kind,
            source_format="notebook",
            output_boundary=boundary,
            target_metadata=tuple(
                sorted(
                    {
                        **cell_metadata,
                        **(
                            {
                                key: value
                                for key, value in (output.metadata if output is not None else ())
                                if key in _CROSSREF_DISPLAY_KEYS
                            }
                        ),
                    }.items()
                )
            ),
            target_span=output.span if output is not None else cell.span,
        )
        for boundary, output in boundaries
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


def _logical_cell_span(document: SourceDocument, cell_index: int, source: str) -> SourceSpan:
    source_document = SourceDocument.from_text(document.path, source, DocumentKind.MARKDOWN)
    end = len(source_document.text)
    end_line, end_col = source_document.line_index.position(max(0, end - 1))
    return SourceSpan(
        path=document.path,
        start=0,
        end=end,
        line=1,
        col=1,
        end_line=end_line,
        end_col=end_col,
        cell=cell_index,
        cell_line=1,
    )
