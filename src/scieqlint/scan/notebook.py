"""Notebook scanner adapter for Markdown cells."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from scieqlint.config.model import Config
from scieqlint.diag.model import Diagnostic
from scieqlint.frontend.notebook_input import (
    NotebookInput,
    NotebookSourceLocationError,
    map_notebook_span,
    notebook_cell_document,
    parse_notebook_input,
)
from scieqlint.frontend.notebook_input import (
    cell_source as _cell_source,
)
from scieqlint.frontend.notebook_input import (
    input_diagnostic as _input_diagnostic,
)
from scieqlint.frontend.notebook_input import (
    schema_diagnostic as _schema_diagnostic,
)
from scieqlint.io.source import SourceDocument
from scieqlint.io.workspace import WorkspaceHost
from scieqlint.scan.base import (
    EquationLabel,
    EquationReference,
    MathBlock,
    ScanResult,
    SymbolDirective,
)
from scieqlint.scan.markdown import MarkdownScanner


class NotebookScanner:
    def __init__(self, *, workspace: WorkspaceHost | None = None) -> None:
        self._markdown = MarkdownScanner(workspace=workspace)

    def parse(self, document: SourceDocument) -> NotebookInput:
        """Decode one notebook and retain its exact JSON source ranges."""

        return parse_notebook_input(document)

    def scan(
        self,
        document: SourceDocument,
        config: Config,
        *,
        parsed: NotebookInput | None = None,
    ) -> ScanResult:
        if parsed is None:
            notebook_input = self.parse(document)
        else:
            if parsed.document is not document:
                raise ValueError("parsed notebook input belongs to a different SourceDocument")
            notebook_input = parsed
        if notebook_input.root is None:
            return ScanResult(blocks=(), diagnostics=notebook_input.diagnostics)

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
            # Parsed notebook input retains one raw range tuple for every
            # logical character in each readable cell source.
            source_ranges = cast(
                tuple[tuple[tuple[int, int], ...], ...],
                notebook_input.cell_source_ranges[cell_index],
            )
            cell_document = notebook_cell_document(document, cell_index, source)
            scan = self._markdown.scan(cell_document, config)
            try:
                mapped_blocks = tuple(
                    replace(
                        block,
                        span=map_notebook_span(
                            document,
                            block.span,
                            cell_index=cell_index,
                            source_ranges=source_ranges,
                        ),
                    )
                    for block in scan.blocks
                )
                mapped_labels = tuple(
                    replace(
                        label,
                        span=map_notebook_span(
                            document,
                            label.span,
                            cell_index=cell_index,
                            source_ranges=source_ranges,
                        ),
                    )
                    for label in scan.labels
                )
                mapped_references = tuple(
                    replace(
                        reference,
                        span=map_notebook_span(
                            document,
                            reference.span,
                            cell_index=cell_index,
                            source_ranges=source_ranges,
                        ),
                    )
                    for reference in scan.references
                )
                mapped_symbol_directives = tuple(
                    replace(
                        directive,
                        span=map_notebook_span(
                            document,
                            directive.span,
                            cell_index=cell_index,
                            source_ranges=source_ranges,
                        ),
                    )
                    for directive in scan.symbol_directives
                )
                mapped_diagnostics = tuple(
                    _with_cell_diagnostic(diagnostic, document, cell_index, source_ranges)
                    for diagnostic in scan.diagnostics
                )
            except NotebookSourceLocationError as exc:
                diagnostics.append(_input_diagnostic(document, exc))
                continue
            blocks.extend(mapped_blocks)
            labels.extend(mapped_labels)
            references.extend(mapped_references)
            symbol_directives.extend(mapped_symbol_directives)
            diagnostics.extend(mapped_diagnostics)

        return ScanResult(
            blocks=tuple(blocks),
            labels=tuple(labels),
            references=tuple(references),
            symbol_directives=tuple(symbol_directives),
            diagnostics=tuple(diagnostics),
        )


def _with_cell_diagnostic(
    diagnostic: Diagnostic,
    document: SourceDocument,
    cell_index: int,
    source_ranges: tuple[tuple[tuple[int, int], ...], ...],
) -> Diagnostic:
    assert diagnostic.span is not None, "Markdown scanner diagnostics retain source spans"
    return replace(
        diagnostic,
        span=map_notebook_span(
            document,
            diagnostic.span,
            cell_index=cell_index,
            source_ranges=source_ranges,
        ),
    )
