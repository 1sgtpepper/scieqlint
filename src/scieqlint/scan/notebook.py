"""Notebook scanner for Markdown cells."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import cast

from scieqlint.config.model import Config
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import (
    EquationLabel,
    EquationReference,
    MathBlock,
    ScanResult,
    SymbolDirective,
)
from scieqlint.scan.markdown import MarkdownScanner

_MAX_JSON_INTEGER_DIGITS = 4096


@dataclass(frozen=True, slots=True)
class NotebookInput:
    """One validated JSON decode shared by notebook scanners and frontends."""

    root: Mapping[str, object] | None
    cells: tuple[object, ...]
    cell_spans: tuple[SourceSpan | None, ...]
    output_spans: tuple[tuple[SourceSpan | None, ...], ...]
    diagnostics: tuple[Diagnostic, ...]
    valid: bool


class NotebookScanner:
    def __init__(self) -> None:
        self._markdown = MarkdownScanner()

    def parse(self, document: SourceDocument) -> NotebookInput:
        """Decode one notebook and retain the source ranges found in its JSON."""

        try:
            notebook_data: object = json.loads(document.text, parse_int=_parse_json_integer)
        except ValueError as exc:
            return NotebookInput(
                root=None,
                cells=(),
                cell_spans=(),
                output_spans=(),
                diagnostics=(_input_diagnostic(document, exc),),
                valid=False,
            )
        if not isinstance(notebook_data, Mapping):
            return NotebookInput(
                root=None,
                cells=(),
                cell_spans=(),
                output_spans=(),
                diagnostics=(_schema_diagnostic(document, "notebook root must be a JSON object"),),
                valid=False,
            )

        notebook = cast(Mapping[str, object], notebook_data)
        raw_cells = notebook.get("cells")
        if not isinstance(raw_cells, list):
            return NotebookInput(
                root=None,
                cells=(),
                cell_spans=(),
                output_spans=(),
                diagnostics=(_schema_diagnostic(document, "notebook cells must be a list"),),
                valid=False,
            )
        cells = tuple(cast(list[object], raw_cells))
        cell_spans, output_spans = _notebook_locations(document, len(cells))
        return NotebookInput(
            root=notebook,
            cells=cells,
            cell_spans=cell_spans,
            output_spans=output_spans,
            diagnostics=_notebook_schema_diagnostics(document, notebook),
            valid=True,
        )

    def scan(
        self,
        document: SourceDocument,
        config: Config,
        *,
        parsed: NotebookInput | None = None,
    ) -> ScanResult:
        notebook_input = parsed or self.parse(document)
        if not notebook_input.valid:
            return ScanResult(blocks=(), diagnostics=notebook_input.diagnostics)
        assert notebook_input.root is not None

        blocks: list[MathBlock] = []
        labels: list[EquationLabel] = []
        references: list[EquationReference] = []
        symbol_directives: list[SymbolDirective] = []
        diagnostics = list(notebook_input.diagnostics)

        for cell_index, raw_cell in enumerate(notebook_input.cells):
            if not isinstance(raw_cell, Mapping):
                diagnostics.append(
                    _schema_diagnostic(
                        document,
                        f"cell {cell_index} must be an object",
                        cell=cell_index,
                    )
                )
                continue
            cell = cast(Mapping[str, object], raw_cell)
            if cell.get("cell_type") != "markdown":
                continue
            source = _cell_source(cell.get("source"))
            if source is None:
                diagnostics.append(
                    _schema_diagnostic(
                        document,
                        f"markdown cell {cell_index} source must be a string or string list",
                        cell=cell_index,
                    )
                )
                continue
            scan = self._markdown.scan(_cell_document(document, cell_index, source), config)
            blocks.extend(_with_cell_block(block, cell_index) for block in scan.blocks)
            labels.extend(_with_cell_label(label, cell_index) for label in scan.labels)
            references.extend(
                _with_cell_reference(reference, cell_index) for reference in scan.references
            )
            symbol_directives.extend(
                _with_cell_symbol_directive(directive, cell_index)
                for directive in scan.symbol_directives
            )
            diagnostics.extend(
                _with_cell_diagnostic(diagnostic, cell_index) for diagnostic in scan.diagnostics
            )

        return ScanResult(
            blocks=tuple(blocks),
            labels=tuple(labels),
            references=tuple(references),
            symbol_directives=tuple(symbol_directives),
            diagnostics=tuple(diagnostics),
        )


def _cell_source(source: object) -> str | None:
    if isinstance(source, str):
        return source
    if isinstance(source, list):
        parts = cast(list[object], source)
        if all(isinstance(part, str) for part in parts):
            return "".join(cast(list[str], parts))
    return None


def _parse_json_integer(text: str) -> int:
    digits = text[1:] if text.startswith("-") else text
    if len(digits) > _MAX_JSON_INTEGER_DIGITS:
        raise ValueError(f"JSON integer exceeds {_MAX_JSON_INTEGER_DIGITS} digits")
    value = 0
    for digit in digits:
        value = value * 10 + ord(digit) - ord("0")
    return -value if text.startswith("-") else value


def _notebook_schema_diagnostics(
    document: SourceDocument,
    notebook: Mapping[str, object],
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    if not _is_json_integer(notebook.get("nbformat")):
        diagnostics.append(_schema_diagnostic(document, "notebook nbformat must be an integer"))
    if not _is_json_integer(notebook.get("nbformat_minor")):
        diagnostics.append(
            _schema_diagnostic(document, "notebook nbformat_minor must be an integer")
        )
    if not isinstance(notebook.get("metadata"), Mapping):
        diagnostics.append(_schema_diagnostic(document, "notebook metadata must be an object"))
    return tuple(diagnostics)


def _notebook_locations(
    document: SourceDocument,
    cell_count: int,
) -> tuple[tuple[SourceSpan | None, ...], tuple[tuple[SourceSpan | None, ...], ...]]:
    """Locate cell and output objects without giving semantic parsing a second owner."""

    cell_spans: list[SourceSpan | None] = [None] * cell_count
    output_spans: list[tuple[SourceSpan | None, ...]] = [()] * cell_count
    try:
        decoder = json.JSONDecoder(parse_int=_parse_json_integer)
        root_start = _skip_json_whitespace(document.text, 0)
        _root, root_end = decoder.raw_decode(document.text, root_start)
        cells_range = _json_object_members(decoder, document.text, root_start, root_end).get(
            "cells"
        )
        if cells_range is None:
            return tuple(cell_spans), tuple(output_spans)
        for cell_index, (cell_start, cell_end) in enumerate(
            _json_array_ranges(decoder, document.text, *cells_range)
        ):
            if cell_index >= cell_count:
                break
            cell_spans[cell_index] = _json_span(document, cell_start, cell_end, cell_index)
            output_range = _json_object_members(
                decoder,
                document.text,
                cell_start,
                cell_end,
            ).get("outputs")
            if output_range is None:
                continue
            output_spans[cell_index] = tuple(
                _json_span(document, output_start, output_end, cell_index)
                for output_start, output_end in _json_array_ranges(
                    decoder,
                    document.text,
                    *output_range,
                )
            )
    except (IndexError, TypeError, ValueError):
        # A valid JSON document can still be outside this location walk's narrow
        # object/array shape.  An absent span is honest; a guessed line is not.
        return tuple(cell_spans), tuple(output_spans)
    return tuple(cell_spans), tuple(output_spans)


def _json_object_members(
    decoder: json.JSONDecoder,
    text: str,
    start: int,
    end: int,
) -> dict[str, tuple[int, int]]:
    if text[_skip_json_whitespace(text, start)] != "{":
        return {}
    position = _skip_json_whitespace(text, start) + 1
    members: dict[str, tuple[int, int]] = {}
    while True:
        position = _skip_json_whitespace(text, position)
        if position >= end or text[position] == "}":
            return members
        key, key_end = decoder.raw_decode(text, position)
        if not isinstance(key, str):
            return {}
        position = _skip_json_whitespace(text, key_end)
        if position >= end or text[position] != ":":
            return {}
        value_start = _skip_json_whitespace(text, position + 1)
        _value, value_end = decoder.raw_decode(text, value_start)
        members[key] = (value_start, value_end)
        position = _skip_json_whitespace(text, value_end)
        if position >= end or text[position] == "}":
            return members
        if text[position] != ",":
            return {}
        position += 1


def _json_array_ranges(
    decoder: json.JSONDecoder,
    text: str,
    start: int,
    end: int,
) -> tuple[tuple[int, int], ...]:
    if text[_skip_json_whitespace(text, start)] != "[":
        return ()
    position = _skip_json_whitespace(text, start) + 1
    ranges: list[tuple[int, int]] = []
    while True:
        position = _skip_json_whitespace(text, position)
        if position >= end or text[position] == "]":
            return tuple(ranges)
        _value, value_end = decoder.raw_decode(text, position)
        ranges.append((position, value_end))
        position = _skip_json_whitespace(text, value_end)
        if position >= end or text[position] == "]":
            return tuple(ranges)
        if text[position] != ",":
            return ()
        position += 1


def _skip_json_whitespace(text: str, start: int) -> int:
    while start < len(text) and text[start] in " \t\r\n":
        start += 1
    return start


def _json_span(
    document: SourceDocument,
    start: int,
    end: int,
    cell: int,
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
    )


def _is_json_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _cell_document(document: SourceDocument, cell_index: int, source: str) -> SourceDocument:
    cell_document = SourceDocument.from_text(document.path, source, DocumentKind.MARKDOWN)
    return replace(
        cell_document,
        display_path=f"{document.display_path}#cell-{cell_index}",
    )


def _with_cell_block(block: MathBlock, cell_index: int) -> MathBlock:
    return replace(block, span=_with_cell_span(block.span, cell_index))


def _with_cell_label(label: EquationLabel, cell_index: int) -> EquationLabel:
    return replace(label, span=_with_cell_span(label.span, cell_index))


def _with_cell_reference(reference: EquationReference, cell_index: int) -> EquationReference:
    return replace(reference, span=_with_cell_span(reference.span, cell_index))


def _with_cell_symbol_directive(
    directive: SymbolDirective,
    cell_index: int,
) -> SymbolDirective:
    return replace(directive, span=_with_cell_span(directive.span, cell_index))


def _with_cell_diagnostic(diagnostic: Diagnostic, cell_index: int) -> Diagnostic:
    if diagnostic.span is None:
        return diagnostic
    return replace(diagnostic, span=_with_cell_span(diagnostic.span, cell_index))


def _with_cell_span(span: SourceSpan, cell_index: int) -> SourceSpan:
    return replace(span, cell=cell_index, cell_line=span.line)


def _input_diagnostic(document: SourceDocument, exc: ValueError) -> Diagnostic:
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
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=info.message,
        span=span,
        detail=exc.msg if isinstance(exc, json.JSONDecodeError) else str(exc),
        rule="input",
    )


def _schema_diagnostic(
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
