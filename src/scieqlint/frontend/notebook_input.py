"""FrontendHost-owned notebook input and exact raw-source location mapping."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import cast

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSegment, SourceSpan
from scieqlint.io.limits import DEFAULT_MAX_FILE_BYTES, DEFAULT_MAX_NOTEBOOK_SOURCE_CHARS
from scieqlint.io.source import DocumentKind, LineIndex, SourceDocument

from .notebook_json import (
    json_array_ranges,
    json_decoder,
    json_object_members,
    json_string_character_ranges,
    parse_json_document,
)

_MARKDOWN_LINE_BOUNDARIES = "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"


def parse_notebook_input(document: SourceDocument) -> NotebookInput:
    """Decode one notebook and retain the source ranges found in its JSON."""

    if len(document.text.encode("utf-8", errors="surrogatepass")) > DEFAULT_MAX_FILE_BYTES:
        return NotebookInput(
            document=document,
            root=None,
            cells=(),
            cell_spans=(),
            output_spans=(),
            output_label_spans=(),
            cell_source_ranges=(),
            diagnostics=(size_diagnostic(document),),
            valid=False,
        )
    try:
        notebook_data, root_range = parse_json_document(document.text)
    except (ValueError, RecursionError) as exc:
        return NotebookInput(
            document=document,
            root=None,
            cells=(),
            cell_spans=(),
            output_spans=(),
            output_label_spans=(),
            cell_source_ranges=(),
            diagnostics=(input_diagnostic(document, exc),),
            valid=False,
        )
    if not isinstance(notebook_data, Mapping):
        return NotebookInput(
            document=document,
            root=None,
            cells=(),
            cell_spans=(),
            output_spans=(),
            output_label_spans=(),
            cell_source_ranges=(),
            diagnostics=(schema_diagnostic(document, "notebook root must be a JSON object"),),
            valid=False,
        )

    notebook = cast(Mapping[str, object], notebook_data)
    raw_cells = notebook.get("cells")
    if not isinstance(raw_cells, list):
        return NotebookInput(
            document=document,
            root=None,
            cells=(),
            cell_spans=(),
            output_spans=(),
            output_label_spans=(),
            cell_source_ranges=(),
            diagnostics=(schema_diagnostic(document, "notebook cells must be a list"),),
            valid=False,
        )
    cells = tuple(cast(list[object], raw_cells))
    try:
        (
            cell_spans,
            output_spans,
            output_label_spans,
            cell_source_ranges,
        ) = _notebook_locations(document, cells, root_range)
    except _NotebookSourceLimitError as exc:
        return NotebookInput(
            document=document,
            root=None,
            cells=(),
            cell_spans=(),
            output_spans=(),
            output_label_spans=(),
            cell_source_ranges=(),
            diagnostics=(size_diagnostic(document, detail=str(exc)),),
            valid=False,
        )
    except (ValueError, RecursionError) as exc:  # pragma: no cover - defensive replay guard
        return NotebookInput(
            document=document,
            root=None,
            cells=(),
            cell_spans=(),
            output_spans=(),
            output_label_spans=(),
            cell_source_ranges=(),
            diagnostics=(input_diagnostic(document, exc),),
            valid=False,
        )
    return NotebookInput(
        document=document,
        root=notebook,
        cells=cells,
        cell_spans=cell_spans,
        output_spans=output_spans,
        output_label_spans=output_label_spans,
        cell_source_ranges=cell_source_ranges,
        diagnostics=_notebook_schema_diagnostics(document, notebook),
        valid=True,
    )


class NotebookSourceLocationError(ValueError):
    """A logical notebook-cell span cannot be mapped to its JSON source."""


class _NotebookSourceLimitError(ValueError):
    """The exact notebook source mapping would exceed its memory budget."""


@dataclass(frozen=True, slots=True)
class NotebookInput:
    """One validated notebook input shared by scanners and frontends."""

    document: SourceDocument
    root: Mapping[str, object] | None
    cells: tuple[object, ...]
    cell_spans: tuple[SourceSpan | None, ...]
    output_spans: tuple[tuple[SourceSpan | None, ...], ...]
    output_label_spans: tuple[tuple[SourceSpan | None, ...], ...]
    cell_source_ranges: tuple[tuple[tuple[tuple[int, int], ...], ...] | None, ...]
    diagnostics: tuple[Diagnostic, ...]
    valid: bool


def cell_source(source: object) -> str | None:
    if isinstance(source, str):
        return source
    if isinstance(source, list):
        parts = cast(list[object], source)
        if all(isinstance(part, str) for part in parts):
            return "".join(cast(list[str], parts))
    return None


def notebook_cell_document(
    document: SourceDocument,
    cell_index: int,
    source: str,
) -> SourceDocument:
    """Build a decoded Markdown cell with the parser's split-line semantics."""

    cell_document = SourceDocument.from_text(document.path, source, DocumentKind.MARKDOWN)
    line_starts = (
        0,
        *(
            index + 1
            for index, character in enumerate(cell_document.text)
            if character in _MARKDOWN_LINE_BOUNDARIES
        ),
    )
    return replace(
        cell_document,
        display_path=f"{document.display_path}#cell-{cell_index}",
        line_index=LineIndex(line_starts),
    )


def _notebook_schema_diagnostics(
    document: SourceDocument,
    notebook: Mapping[str, object],
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    if not _is_json_integer(notebook.get("nbformat")):
        diagnostics.append(schema_diagnostic(document, "notebook nbformat must be an integer"))
    if not _is_json_integer(notebook.get("nbformat_minor")):
        diagnostics.append(
            schema_diagnostic(document, "notebook nbformat_minor must be an integer")
        )
    if not isinstance(notebook.get("metadata"), Mapping):
        diagnostics.append(schema_diagnostic(document, "notebook metadata must be an object"))
    return tuple(diagnostics)


def _notebook_locations(
    document: SourceDocument,
    cells: tuple[object, ...],
    root_range: tuple[int, int],
) -> tuple[
    tuple[SourceSpan | None, ...],
    tuple[tuple[SourceSpan | None, ...], ...],
    tuple[tuple[SourceSpan | None, ...], ...],
    tuple[tuple[tuple[tuple[int, int], ...], ...] | None, ...],
]:
    """Locate notebook objects and exact decoded cell-source ranges in one pass."""

    source_characters = 0
    for raw_cell in cells:
        if not isinstance(raw_cell, Mapping):
            continue
        cell = cast(Mapping[str, object], raw_cell)
        if cell.get("cell_type") != "markdown":
            continue
        source_length = _source_character_length(cell.get("source"))
        if source_length is None:
            continue
        source_characters += source_length
        if source_characters > DEFAULT_MAX_NOTEBOOK_SOURCE_CHARS:
            raise _NotebookSourceLimitError(
                "normalized notebook Markdown source exceeds "
                f"{DEFAULT_MAX_NOTEBOOK_SOURCE_CHARS} logical characters"
            )

    cell_spans: list[SourceSpan | None] = [None] * len(cells)
    output_spans: list[tuple[SourceSpan | None, ...]] = [()] * len(cells)
    output_label_spans: list[tuple[SourceSpan | None, ...]] = [()] * len(cells)
    cell_source_ranges: list[tuple[tuple[tuple[int, int], ...], ...] | None] = [None] * len(cells)
    decoder = json_decoder()
    root_start, root_end = root_range
    root_members = json_object_members(decoder, document.text, root_start, root_end)
    cells_range = root_members["cells"]
    cell_ranges = json_array_ranges(decoder, document.text, *cells_range)
    for cell_index, (cell, (cell_start, cell_end)) in enumerate(
        zip(cells, cell_ranges, strict=True)
    ):
        cell_spans[cell_index] = _json_span(
            document,
            cell_start,
            cell_end,
            cell_index,
            cell_line=1,
        )
        if not isinstance(cell, Mapping):
            continue
        cell = cast(Mapping[str, object], cell)
        cell_members = json_object_members(decoder, document.text, cell_start, cell_end)
        if cell.get("cell_type") == "markdown":
            source = cell_source(cell.get("source"))
            source_ranges = (
                None
                if source is None
                else _source_ranges(decoder, document.text, cell_members["source"])
            )
            cell_source_ranges[cell_index] = source_ranges
        raw_outputs = cell.get("outputs")
        if not isinstance(raw_outputs, list):
            continue
        output_ranges = json_array_ranges(
            decoder,
            document.text,
            *cell_members["outputs"],
        )
        output_spans[cell_index] = tuple(
            _json_span(document, output_start, output_end, cell_index)
            for output_start, output_end in output_ranges
        )
        output_label_spans[cell_index] = _output_label_spans(
            decoder,
            document,
            cell_index,
            cast(list[object], raw_outputs),
            output_ranges,
        )
    return (
        tuple(cell_spans),
        tuple(output_spans),
        tuple(output_label_spans),
        tuple(cell_source_ranges),
    )


def _output_label_spans(
    decoder: json.JSONDecoder,
    document: SourceDocument,
    cell_index: int,
    outputs: list[object],
    output_ranges: tuple[tuple[int, int], ...],
) -> tuple[SourceSpan | None, ...]:
    spans: list[SourceSpan | None] = []
    for output, output_range in zip(outputs, output_ranges, strict=True):
        if not isinstance(output, Mapping):
            spans.append(None)
            continue
        output = cast(Mapping[str, object], output)
        output_members = json_object_members(decoder, document.text, *output_range)
        metadata = output.get("metadata")
        if not isinstance(metadata, Mapping):
            spans.append(None)
            continue
        metadata = cast(Mapping[str, object], metadata)
        metadata_members = json_object_members(
            decoder,
            document.text,
            *output_members["metadata"],
        )
        label_key = next(
            (key for key in ("label", "lst-label") if _option_value_present(metadata.get(key))),
            None,
        )
        if label_key is None:
            spans.append(None)
            continue
        spans.append(
            _json_value_span(
                document,
                metadata_members[label_key],
                cell=cell_index,
                cell_line=1,
            )
        )
    return tuple(spans)


def _option_value_present(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, list):
        items = cast(list[object], value)
        return all(isinstance(item, (str, int, float, bool)) for item in items)
    return False


def _source_character_length(source: object) -> int | None:
    if isinstance(source, str):
        return _normalized_character_length((source,))
    if not isinstance(source, list):
        return None
    parts = cast(list[object], source)
    if not all(isinstance(part, str) for part in parts):
        return None
    return _normalized_character_length(cast(list[str], parts))


def _normalized_character_length(parts: tuple[str, ...] | list[str]) -> int:
    length = 0
    previous_was_cr = False
    for part in parts:
        for character in part:
            length += 1
            if previous_was_cr and character == "\n":
                length -= 1
            previous_was_cr = character == "\r"
    return length


def _source_ranges(
    decoder: json.JSONDecoder,
    text: str,
    source_range: tuple[int, int],
) -> tuple[tuple[tuple[int, int], ...], ...]:
    """Map normalized decoded source characters to raw JSON offsets."""

    start, end = source_range
    ranges: list[tuple[str, int, int]] = []
    if text[start] == '"':
        ranges.extend(json_string_character_ranges(text, start, end))
    else:
        for item_start, item_end in json_array_ranges(decoder, text, start, end):
            ranges.extend(json_string_character_ranges(text, item_start, item_end))

    normalized: list[tuple[tuple[int, int], ...]] = []
    range_index = 0
    while range_index < len(ranges):
        character, raw_start, raw_end = ranges[range_index]
        if (
            character == "\r"
            and range_index + 1 < len(ranges)
            and ranges[range_index + 1][0] == "\n"
        ):
            # SourceDocument normalizes CRLF to one character. Keep both raw
            # ranges so a list boundary or an escape cannot corrupt offsets.
            normalized.append(
                ((raw_start, raw_end), (ranges[range_index + 1][1], ranges[range_index + 1][2]))
            )
            range_index += 2
            continue
        normalized.append(((raw_start, raw_end),))
        range_index += 1
    return tuple(normalized)


def _json_value_span(
    document: SourceDocument,
    value_range: tuple[int, int],
    *,
    cell: int | None,
    cell_line: int | None,
) -> SourceSpan:
    start, end = value_range
    if document.text[start] != '"':
        return _json_span(document, start, end, cell, cell_line=cell_line)
    return _json_span(
        document,
        start + 1,
        end - 1,
        cell,
        cell_line=cell_line,
    )


def _json_span(
    document: SourceDocument,
    start: int,
    end: int,
    cell: int | None,
    *,
    cell_line: int | None = None,
) -> SourceSpan:
    line, col = document.line_index.position(start)
    end_line, end_col = document.line_index.position(max(start, end - 1))
    return SourceSpan(
        path=document.path,
        start=start,
        end=end,
        line=line,
        col=col,
        end_line=end_line,
        end_col=end_col,
        cell=cell,
        cell_line=cell_line,
    )


def map_notebook_span(
    document: SourceDocument,
    span: SourceSpan,
    *,
    cell_index: int,
    source_ranges: tuple[tuple[tuple[int, int], ...], ...],
) -> SourceSpan:
    """Map one logical cell span to raw JSON and retain each character's ranges."""

    if not source_ranges:
        raise NotebookSourceLocationError(
            f"notebook cell {cell_index} source has no character ranges"
        )
    if span.start < 0 or span.end < span.start or span.end > len(source_ranges):
        raise NotebookSourceLocationError(
            f"notebook cell {cell_index} source location is outside its source"
        )
    if span.start == span.end:
        position = (
            source_ranges[span.start][0][0]
            if span.start < len(source_ranges)
            else source_ranges[-1][-1][1]
        )
        start = position
        end = position
        segments: tuple[SourceSegment, ...] = ()
    else:
        segments = tuple(
            _source_segment(document, ranges) for ranges in source_ranges[span.start : span.end]
        )
        start = segments[0].start
        end = segments[-1].end
    line, col = document.line_index.position(start)
    end_line, end_col = document.line_index.position(max(start, end - 1))
    return SourceSpan(
        path=document.path,
        start=start,
        end=end,
        line=line,
        col=col,
        end_line=end_line,
        end_col=end_col,
        cell=cell_index,
        cell_line=span.line,
        segments=segments,
    )


def _source_segment(
    document: SourceDocument,
    ranges: tuple[tuple[int, int], ...],
) -> SourceSegment:
    """Build one logical-character segment from its exact raw ranges."""

    if not ranges:
        raise NotebookSourceLocationError("notebook source character has no raw range")
    start = ranges[0][0]
    end = ranges[-1][1]
    line, col = document.line_index.position(start)
    end_line, end_col = document.line_index.position(max(start, end - 1))
    return SourceSegment(
        ranges=ranges,
        line=line,
        col=col,
        end_line=end_line,
        end_col=end_col,
    )


def _is_json_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def input_diagnostic(document: SourceDocument, exc: ValueError | RecursionError) -> Diagnostic:
    """Build the shared input diagnostic for a malformed notebook."""

    info = CATALOG["INP001"]
    if isinstance(exc, json.JSONDecodeError):
        span = SourceSpan(
            path=document.path,
            start=exc.pos,
            end=exc.pos,
            line=exc.lineno,
            col=exc.colno,
            end_line=exc.lineno,
            end_col=exc.colno,
        )
    else:
        span = _file_start_span(document)
    detail = (
        "maximum JSON nesting depth exceeded"
        if isinstance(exc, RecursionError)
        else exc.msg
        if isinstance(exc, json.JSONDecodeError)
        else str(exc)
    )
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=info.message,
        span=span,
        detail=detail,
        rule="input",
    )


def size_diagnostic(document: SourceDocument, *, detail: str | None = None) -> Diagnostic:
    """Build the fixed resource-limit diagnostic for notebook input."""

    info = CATALOG["INP003"]
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=info.message,
        span=_file_start_span(document),
        detail=detail or f"normalized notebook text exceeds {DEFAULT_MAX_FILE_BYTES} UTF-8 bytes",
        rule="input",
    )


def schema_diagnostic(
    document: SourceDocument,
    detail: str,
    *,
    cell: int | None = None,
) -> Diagnostic:
    info = CATALOG["INP002"]
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=info.message,
        span=_file_start_span(document, cell=cell),
        detail=detail,
        rule="input",
    )


def _file_start_span(document: SourceDocument, *, cell: int | None = None) -> SourceSpan:
    return SourceSpan(
        path=document.path,
        start=0,
        end=0,
        line=1,
        col=1,
        end_line=1,
        end_col=1,
        cell=cell,
    )
