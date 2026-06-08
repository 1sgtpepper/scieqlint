"""Notebook scanner for Markdown cells."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from scieqlint.config.model import Config
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import EquationLabel, EquationReference, MathBlock, ScanResult
from scieqlint.scan.markdown import MarkdownScanner


class NotebookScanner:
    def __init__(self) -> None:
        self._markdown = MarkdownScanner()

    def scan(self, document: SourceDocument, config: Config) -> ScanResult:
        try:
            notebook_data: object = json.loads(document.text)
        except json.JSONDecodeError as exc:
            return ScanResult(
                blocks=(), diagnostics=(_input_diagnostic(document, exc),)
            )
        if not isinstance(notebook_data, Mapping):
            return ScanResult(blocks=())

        notebook = cast(Mapping[str, object], notebook_data)
        raw_cells = notebook.get("cells")
        if not isinstance(raw_cells, list):
            return ScanResult(blocks=())

        cells = cast(list[object], raw_cells)
        blocks: list[MathBlock] = []
        labels: list[EquationLabel] = []
        references: list[EquationReference] = []
        diagnostics: list[Diagnostic] = []

        for cell_index, raw_cell in enumerate(cells):
            if not isinstance(raw_cell, Mapping):
                continue
            cell = cast(Mapping[str, object], raw_cell)
            if cell.get("cell_type") != "markdown":
                continue
            source = _cell_source(cell.get("source"))
            if source is None:
                continue
            scan = self._markdown.scan(
                _cell_document(document, cell_index, source), config
            )
            blocks.extend(_with_cell_block(block, cell_index) for block in scan.blocks)
            labels.extend(_with_cell_label(label, cell_index) for label in scan.labels)
            references.extend(
                _with_cell_reference(reference, cell_index)
                for reference in scan.references
            )
            diagnostics.extend(
                _with_cell_diagnostic(diagnostic, cell_index)
                for diagnostic in scan.diagnostics
            )

        return ScanResult(
            blocks=tuple(blocks),
            labels=tuple(labels),
            references=tuple(references),
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


def _cell_document(
    document: SourceDocument, cell_index: int, source: str
) -> SourceDocument:
    cell_document = SourceDocument.from_text(
        document.path, source, DocumentKind.MARKDOWN
    )
    return replace(
        cell_document,
        display_path=f"{document.display_path}#cell-{cell_index}",
    )


def _with_cell_block(block: MathBlock, cell_index: int) -> MathBlock:
    return replace(block, span=_with_cell_span(block.span, cell_index))


def _with_cell_label(label: EquationLabel, cell_index: int) -> EquationLabel:
    return replace(label, span=_with_cell_span(label.span, cell_index))


def _with_cell_reference(
    reference: EquationReference, cell_index: int
) -> EquationReference:
    return replace(reference, span=_with_cell_span(reference.span, cell_index))


def _with_cell_diagnostic(diagnostic: Diagnostic, cell_index: int) -> Diagnostic:
    if diagnostic.span is None:
        return diagnostic
    return replace(diagnostic, span=_with_cell_span(diagnostic.span, cell_index))


def _with_cell_span(span: SourceSpan, cell_index: int) -> SourceSpan:
    return replace(span, cell=cell_index, cell_line=span.line)


def _input_diagnostic(
    document: SourceDocument, exc: json.JSONDecodeError
) -> Diagnostic:
    info = CATALOG["INP001"]
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=info.message,
        span=SourceSpan(
            path=document.path,
            start=exc.pos,
            end=exc.pos,
            line=exc.lineno,
            col=exc.colno,
            end_line=exc.lineno,
            end_col=exc.colno,
        ),
        detail=exc.msg,
        rule="input",
    )
