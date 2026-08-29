"""FrontendHost-owned notebook input and exact raw-source location mapping."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from typing import cast

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSegment, SourceSpan
from scieqlint.io.limits import DEFAULT_MAX_FILE_BYTES, DEFAULT_MAX_NOTEBOOK_SOURCE_CHARS
from scieqlint.io.source import DocumentKind, LineIndex, SourceDocument

from .notebook_json import (
    iter_json_string_character_ranges,
    json_array_ranges,
    json_decoder,
    json_object_members,
    parse_json_document,
)

_MARKDOWN_LINE_BOUNDARIES = "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"
_NOTEBOOK_OPTION_RE = re.compile(r"^[ \t]*#\|[ \t]*(?P<key>[A-Za-z0-9_.-]+):[ \t]*(?P<value>.*)$")


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
            cell_option_spans=(),
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
            cell_option_spans=(),
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
            cell_option_spans=(),
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
            cell_option_spans=(),
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
            cell_option_spans,
        ) = _notebook_locations(document, notebook, cells, root_range)
    except _NotebookSourceLimitError as exc:
        return NotebookInput(
            document=document,
            root=None,
            cells=(),
            cell_spans=(),
            output_spans=(),
            output_label_spans=(),
            cell_source_ranges=(),
            cell_option_spans=(),
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
            cell_option_spans=(),
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
        cell_option_spans=cell_option_spans,
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
    cell_option_spans: tuple[tuple[tuple[str, SourceSpan], ...] | None, ...]
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
    notebook: Mapping[str, object],
    cells: tuple[object, ...],
    root_range: tuple[int, int],
) -> tuple[
    tuple[SourceSpan | None, ...],
    tuple[tuple[SourceSpan | None, ...], ...],
    tuple[tuple[SourceSpan | None, ...], ...],
    tuple[tuple[tuple[tuple[int, int], ...], ...] | None, ...],
    tuple[tuple[tuple[str, SourceSpan], ...] | None, ...],
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
    cell_option_spans: list[tuple[tuple[str, SourceSpan], ...] | None] = [None] * len(cells)
    decoder = json_decoder()
    root_start, root_end = root_range
    root_members = json_object_members(decoder, document.text, root_start, root_end)
    cells_range = root_members["cells"]
    default_language_span = _default_language_span(
        decoder,
        document,
        root_members,
        notebook,
    )
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
        source = cell_source(cell.get("source"))
        if cell.get("cell_type") == "markdown":
            cell_source_ranges[cell_index] = (
                None
                if source is None
                else _source_ranges(decoder, document.text, cell_members["source"])
            )
        elif cell.get("cell_type") == "code":
            cell_option_spans[cell_index] = _cell_option_spans(
                decoder,
                document,
                cell_index,
                cell,
                cell_members,
                source,
                cell_members.get("source"),
                default_language_span,
            )
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
        tuple(cell_option_spans),
    )


def _default_language_span(
    decoder: json.JSONDecoder,
    document: SourceDocument,
    root_members: Mapping[str, tuple[int, int]],
    notebook: Mapping[str, object],
) -> SourceSpan | None:
    metadata = notebook.get("metadata")
    metadata_range = root_members.get("metadata")
    if not isinstance(metadata, Mapping) or metadata_range is None:
        return None
    metadata = cast(Mapping[str, object], metadata)
    metadata_members = json_object_members(decoder, document.text, *metadata_range)
    for parent_key, value_key in (("kernelspec", "language"), ("language_info", "name")):
        parent = metadata.get(parent_key)
        parent_range = metadata_members.get(parent_key)
        if not isinstance(parent, Mapping) or parent_range is None:
            continue
        parent = cast(Mapping[str, object], parent)
        value = parent.get(value_key)
        value_range = json_object_members(decoder, document.text, *parent_range).get(value_key)
        if not isinstance(value, str) or not value.strip() or value_range is None:
            continue
        return _json_value_span(
            document,
            value_range,
            cell=None,
            cell_line=None,
        )
    return None


def _cell_option_spans(
    decoder: json.JSONDecoder,
    document: SourceDocument,
    cell_index: int,
    cell: Mapping[str, object],
    cell_members: Mapping[str, tuple[int, int]],
    source: str | None,
    source_range: tuple[int, int] | None,
    default_language_span: SourceSpan | None,
) -> tuple[tuple[str, SourceSpan], ...]:
    """Locate code-cell label options without losing JSON source identity."""

    spans: dict[str, SourceSpan] = {}
    metadata = cell.get("metadata")
    if isinstance(metadata, Mapping) and "metadata" in cell_members:
        metadata = cast(Mapping[str, object], metadata)
        metadata_members = json_object_members(
            decoder,
            document.text,
            *cell_members["metadata"],
        )
        _record_option_spans(document, cell_index, metadata, metadata_members, spans)
        quarto = metadata.get("quarto")
        if isinstance(quarto, Mapping) and "quarto" in metadata_members:
            quarto = cast(Mapping[str, object], quarto)
            quarto_members = json_object_members(
                decoder,
                document.text,
                *metadata_members["quarto"],
            )
            _record_option_spans(document, cell_index, quarto, quarto_members, spans)

    if source is not None and source_range is not None:
        source_options: dict[str, tuple[int, int, int] | None] = {}
        for key, value, start, end, line in _source_option_entries(source):
            if key not in {"label", "language"}:
                continue
            source_options[key] = None if key == "label" and not value else (start, end, line)
        for key, option_range in source_options.items():
            if option_range is None:
                spans.pop(key, None)
            else:
                spans[key] = _source_option_span(
                    decoder,
                    document,
                    source_range,
                    *option_range,
                    cell_index=cell_index,
                )
    if "language" not in spans and default_language_span is not None:
        spans["language"] = replace(default_language_span, cell=cell_index, cell_line=1)
    return tuple(sorted(spans.items()))


def _source_option_span(
    decoder: json.JSONDecoder,
    document: SourceDocument,
    source_range: tuple[int, int],
    start: int,
    end: int,
    cell_line: int,
    *,
    cell_index: int,
) -> SourceSpan:
    if start == end:
        position = _source_position(decoder, document.text, source_range, start)
        line, col = document.line_index.position(position)
        return SourceSpan(
            path=document.path,
            start=position,
            end=position,
            line=line,
            col=col,
            end_line=line,
            end_col=col,
            cell=cell_index,
            cell_line=cell_line,
            segments=(),
        )
    source_ranges = tuple(
        _source_range_slice(
            decoder,
            document.text,
            source_range,
            start,
            end,
        )
    )
    return _mapped_notebook_span(
        document,
        cell_index=cell_index,
        cell_line=cell_line,
        source_ranges=source_ranges,
    )


def _source_position(
    decoder: json.JSONDecoder,
    text: str,
    source_range: tuple[int, int],
    offset: int,
) -> int:
    logical_position = 0
    last_raw_end: int | None = None
    for ranges in _normalized_source_ranges(decoder, text, source_range):
        if logical_position == offset:
            return ranges[0][0]
        logical_position += 1
        last_raw_end = ranges[-1][1]
    if logical_position == offset and last_raw_end is not None:
        return last_raw_end
    raise NotebookSourceLocationError("notebook source position is outside its source")


def _record_option_spans(
    document: SourceDocument,
    cell_index: int,
    options: Mapping[str, object],
    members: Mapping[str, tuple[int, int]],
    spans: dict[str, SourceSpan],
) -> None:
    for key in ("label", "language"):
        if key not in options or key not in members:
            continue
        raw_value = options[key]
        if key != "language" and not _option_value_present(raw_value):
            spans.pop(key, None)
            continue
        if key == "language" and raw_value == "":
            spans[key] = _json_span(
                document,
                *members[key],
                cell=cell_index,
                cell_line=1,
            )
            continue
        spans[key] = _json_value_span(
            document,
            members[key],
            cell=cell_index,
            cell_line=1,
        )


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


def _source_option_entries(text: str) -> Iterator[tuple[str, str, int, int, int]]:
    logical_start = 0
    for line_number, (raw_start, content_end, raw_end) in enumerate(
        _source_line_ranges(text), start=1
    ):
        content = text[raw_start:content_end]
        logical_width = len(content) + (raw_end > content_end)
        stripped = content.strip()
        if not stripped or (stripped.startswith("#") and not stripped.startswith("#|")):
            logical_start += logical_width
            continue
        match = _NOTEBOOK_OPTION_RE.match(content)
        if match is None:
            break
        raw_value = match.group("value")
        value = raw_value.strip()
        leading = len(raw_value) - len(raw_value.lstrip())
        value_start = logical_start + match.start("value") + leading
        logical_start += logical_width
        yield match.group("key"), value, value_start, value_start + len(value), line_number


def _source_line_ranges(text: str) -> Iterator[tuple[int, int, int]]:
    """Yield content ranges with the same boundaries as ``str.splitlines``."""

    start = 0
    position = 0
    while position < len(text):
        character = text[position]
        if character not in _MARKDOWN_LINE_BOUNDARIES:
            position += 1
            continue
        content_end = position
        position += 1
        if character == "\r" and position < len(text) and text[position] == "\n":
            position += 1
        yield start, content_end, position
        start = position
    if start < len(text):
        yield start, len(text), len(text)


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

    return tuple(_normalized_source_ranges(decoder, text, source_range))


def _source_range_slice(
    decoder: json.JSONDecoder,
    text: str,
    source_range: tuple[int, int],
    start: int,
    end: int,
) -> Iterator[tuple[tuple[int, int], ...]]:
    """Yield one exact logical source slice without retaining its prefix."""

    # Option entries are non-empty slices derived from the same decoded source.
    if start < 0 or end <= start:  # pragma: no cover - internal span invariant
        raise NotebookSourceLocationError("notebook source slice is empty or invalid")
    for logical_position, ranges in enumerate(
        _normalized_source_ranges(decoder, text, source_range)
    ):
        if logical_position >= start:
            yield ranges
        if logical_position + 1 == end:
            return
    # Exhaustion would mean the decoded source and its raw JSON replay disagree.
    raise NotebookSourceLocationError(  # pragma: no cover - internal replay invariant
        "notebook source slice is outside its source"
    )


def _normalized_source_ranges(
    decoder: json.JSONDecoder,
    text: str,
    source_range: tuple[int, int],
) -> Iterator[tuple[tuple[int, int], ...]]:
    pending_cr: tuple[int, int] | None = None
    for character, raw_start, raw_end in _source_character_ranges(
        decoder,
        text,
        source_range,
    ):
        raw_range = (raw_start, raw_end)
        if pending_cr is not None:
            if character == "\n":
                yield pending_cr, raw_range
                pending_cr = None
                continue
            yield (pending_cr,)
            pending_cr = None
        if character == "\r":
            pending_cr = raw_range
        else:
            yield (raw_range,)
    if pending_cr is not None:
        yield (pending_cr,)


def _source_character_ranges(
    decoder: json.JSONDecoder,
    text: str,
    source_range: tuple[int, int],
) -> Iterator[tuple[str, int, int]]:
    start, end = source_range
    if text[start] == '"':
        yield from iter_json_string_character_ranges(text, start, end)
        return
    for item_start, item_end in json_array_ranges(decoder, text, start, end):
        yield from iter_json_string_character_ranges(text, item_start, item_end)


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
    if span.start != span.end:
        return _mapped_notebook_span(
            document,
            cell_index=cell_index,
            cell_line=span.line,
            source_ranges=source_ranges[span.start : span.end],
        )
    position = (
        source_ranges[span.start][0][0]
        if span.start < len(source_ranges)
        else source_ranges[-1][-1][1]
    )
    line, col = document.line_index.position(position)
    return SourceSpan(
        path=document.path,
        start=position,
        end=position,
        line=line,
        col=col,
        end_line=line,
        end_col=col,
        cell=cell_index,
        cell_line=span.line,
        segments=(),
    )


def _mapped_notebook_span(
    document: SourceDocument,
    *,
    cell_index: int,
    cell_line: int,
    source_ranges: tuple[tuple[tuple[int, int], ...], ...],
) -> SourceSpan:
    """Build one non-empty raw notebook span from exact logical ranges."""

    # Public mapping validates ranges; option slices are non-empty by construction.
    if not source_ranges:  # pragma: no cover - internal span invariant
        raise NotebookSourceLocationError(
            f"notebook cell {cell_index} source span has no character ranges"
        )
    segments = tuple(_source_segment(document, ranges) for ranges in source_ranges)
    start = segments[0].start
    end = segments[-1].end
    line, col = document.line_index.position(start)
    end_line, end_col = document.line_index.position(end - 1)
    return SourceSpan(
        path=document.path,
        start=start,
        end=end,
        line=line,
        col=col,
        end_line=end_line,
        end_col=end_col,
        cell=cell_index,
        cell_line=cell_line,
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
