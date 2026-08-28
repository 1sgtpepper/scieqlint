"""Notebook frontend façade and fact-snapshot orchestration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from scieqlint.facts.generated import GeneratedFormulaFact
from scieqlint.facts.math import DisplayMathFact, InlineMathFact, UnknownMathFact
from scieqlint.facts.reference import (
    CrossrefMetadataFact,
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    TargetAnchorFact,
)
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import CodeCellFact, NotebookOutputFact
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.io.workspace import WorkspaceHost

from .notebook_cells import (
    cell_source as _cell_source,
)
from .notebook_cells import (
    code_cell_fact as _code_cell_fact,
)
from .notebook_cells import (
    notebook_language as _notebook_language,
)
from .notebook_input import (
    NotebookInput,
    NotebookSourceLocationError,
    parse_notebook_input,
)
from .notebook_markdown import markdown_cell_references as _markdown_cell_references
from .notebook_outputs import (
    crossref_facts as _crossref_facts,
)
from .notebook_outputs import (
    notebook_output_facts as _notebook_output_facts,
)
from .notebook_outputs import (
    output_target_anchors as _output_target_anchors,
)


class NotebookFrontend:
    """Lower notebook metadata and Markdown references without execution."""

    def __init__(self, *, workspace: WorkspaceHost | None = None) -> None:
        self.workspace = workspace or WorkspaceHost()

    def lower(
        self,
        documents: Sequence[SourceDocument],
        *,
        parsed: Mapping[str, NotebookInput] | None = None,
        _source_location_errors: (
            list[tuple[SourceDocument, NotebookSourceLocationError]] | None
        ) = None,
        _include_markdown: bool = True,
    ) -> FactSnapshot:
        parts = tuple(
            _lower_document(
                document,
                parsed=None if parsed is None else parsed.get(document.path.as_posix()),
                source_location_errors=_source_location_errors,
                workspace=self.workspace,
                include_markdown=_include_markdown,
            )
            for document in documents
        )
        all_inline_math = tuple(fact for part in parts for fact in part.inline_math)
        all_display_math = tuple(fact for part in parts for fact in part.display_math)
        all_unknown_math = tuple(fact for part in parts for fact in part.unknown_math)
        all_generated_formulas = tuple(fact for part in parts for fact in part.generated_formulas)
        all_code_cells = tuple(fact for part in parts for fact in part.code_cells)
        return FactSnapshot(
            documents=tuple(document for part in parts for document in part.documents),
            project_members=self.workspace.project_members(documents),
            inline_math=all_inline_math,
            display_math=all_display_math,
            unknown_math=all_unknown_math,
            generated_formulas=all_generated_formulas,
            code_cells=all_code_cells,
            notebook_outputs=tuple(fact for part in parts for fact in part.notebook_outputs),
            target_anchors=tuple(fact for part in parts for fact in part.target_anchors),
            generic_refs=tuple(fact for part in parts for fact in part.generic_refs),
            equation_labels=tuple(fact for part in parts for fact in part.equation_labels),
            equation_refs=tuple(fact for part in parts for fact in part.equation_refs),
            crossref_metadata=tuple(fact for part in parts for fact in part.crossref_metadata),
        )


def _lower_document(
    document: SourceDocument,
    *,
    parsed: NotebookInput | None,
    source_location_errors: list[tuple[SourceDocument, NotebookSourceLocationError]] | None,
    workspace: WorkspaceHost,
    include_markdown: bool,
) -> FactSnapshot:
    if document.kind is not DocumentKind.NOTEBOOK:
        raise ValueError("NotebookFrontend requires notebook documents")
    if parsed is not None and parsed.document is not document:
        raise ValueError("parsed notebook input belongs to a different SourceDocument")
    notebook_input = parsed if parsed is not None else parse_notebook_input(document)
    if not notebook_input.valid:
        return FactSnapshot(documents=(document,))
    assert notebook_input.root is not None
    notebook = notebook_input.root

    default_language = _notebook_language(notebook.get("metadata"))
    cells: list[CodeCellFact] = []
    inline_math: list[InlineMathFact] = []
    display_math: list[DisplayMathFact] = []
    unknown_math: list[UnknownMathFact] = []
    generated_formulas: list[GeneratedFormulaFact] = []
    outputs: list[NotebookOutputFact] = []
    generic_refs: list[GenericRefFact] = []
    equation_labels: list[EquationLabelFact] = []
    equation_refs: list[EquationRefFact] = []
    crossrefs: list[CrossrefMetadataFact] = []
    target_anchors: list[TargetAnchorFact] = []
    for cell_index, raw_cell in enumerate(notebook_input.cells):
        if not isinstance(raw_cell, Mapping):
            continue
        cell = cast(Mapping[str, object], raw_cell)
        if cell.get("cell_type") == "markdown":
            if not include_markdown:
                continue
            source = _cell_source(cell.get("source"))
            if source is not None:
                try:
                    markdown_snapshot = _markdown_cell_references(
                        document,
                        cell_index,
                        source,
                        workspace=workspace,
                        source_ranges=cast(
                            tuple[tuple[tuple[int, int], ...], ...],
                            notebook_input.cell_source_ranges[cell_index],
                        ),
                    )
                except NotebookSourceLocationError as exc:
                    if source_location_errors is not None:
                        source_location_errors.append((document, exc))
                    # Keep profile lowering fail-closed and do not retain a
                    # partial cell snapshot.
                    continue
                target_anchors.extend(markdown_snapshot.target_anchors)
                inline_math.extend(markdown_snapshot.inline_math)
                display_math.extend(markdown_snapshot.display_math)
                unknown_math.extend(markdown_snapshot.unknown_math)
                generated_formulas.extend(markdown_snapshot.generated_formulas)
                generic_refs.extend(markdown_snapshot.generic_refs)
                equation_labels.extend(markdown_snapshot.equation_labels)
                equation_refs.extend(markdown_snapshot.equation_refs)
                crossrefs.extend(markdown_snapshot.crossref_metadata)
            continue
        if cell.get("cell_type") != "code":
            continue
        source = _cell_source(cell.get("source"))
        cell_fact = _code_cell_fact(
            document,
            cell_index,
            cell,
            default_language=default_language,
            cell_span=(
                notebook_input.cell_spans[cell_index]
                if cell_index < len(notebook_input.cell_spans)
                else None
            ),
        )
        cell_outputs = _notebook_output_facts(
            document,
            cell_index,
            cell,
            cell_fact_id=cell_fact.fact_id,
            output_spans=(
                notebook_input.output_spans[cell_index]
                if cell_index < len(notebook_input.output_spans)
                else ()
            ),
        )
        cells.append(cell_fact)
        outputs.extend(cell_outputs)
        output_label_spans = (
            notebook_input.output_label_spans[cell_index]
            if cell_index < len(notebook_input.output_label_spans)
            else ()
        )
        target_anchors.extend(
            _output_target_anchors(
                cell_fact,
                cell_outputs,
                output_label_spans=output_label_spans,
            )
        )
        crossrefs.extend(
            _crossref_facts(
                cell_fact,
                cell_outputs,
                workspace=workspace,
                output_label_spans=output_label_spans,
            )
        )
    return FactSnapshot(
        documents=(document,),
        inline_math=tuple(inline_math),
        display_math=tuple(display_math),
        unknown_math=tuple(unknown_math),
        generated_formulas=tuple(generated_formulas),
        code_cells=tuple(cells),
        notebook_outputs=tuple(outputs),
        target_anchors=tuple(target_anchors),
        generic_refs=tuple(generic_refs),
        equation_labels=tuple(equation_labels),
        equation_refs=tuple(equation_refs),
        crossref_metadata=tuple(crossrefs),
    )
