"""Remap Markdown-cell facts to their original notebook source identity."""

from __future__ import annotations

from dataclasses import replace

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.math import InlineMathFact
from scieqlint.facts.reference import EquationLabelFact, EquationRefFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.io.source import SourceDocument
from scieqlint.io.workspace import WorkspaceHost

from .myst import MySTFrontend
from .myst_shared import inline_math_accessibility_id
from .notebook_input import map_notebook_span, notebook_cell_document


def markdown_cell_references(
    document: SourceDocument,
    cell_index: int,
    source: str,
    *,
    workspace: WorkspaceHost,
    source_ranges: tuple[tuple[tuple[int, int], ...], ...],
) -> FactSnapshot:
    cell_document = notebook_cell_document(document, cell_index, source)
    snapshot = MySTFrontend(workspace=workspace).lower((cell_document,))
    prefix = f"{document.path.as_posix()}::notebook-cell::{cell_index}::"

    def span(value: SourceSpan | None) -> SourceSpan | None:
        if value is None:
            return None
        return map_notebook_span(
            document,
            value,
            cell_index=cell_index,
            source_ranges=source_ranges,
        )

    source_facts = (
        *snapshot.inline_math,
        *snapshot.display_math,
        *snapshot.unknown_math,
        *snapshot.generated_formulas,
        *snapshot.target_anchors,
        *snapshot.generic_refs,
        *snapshot.equation_labels,
        *snapshot.equation_refs,
        *snapshot.crossref_metadata,
    )
    fact_ids = {fact.fact_id: f"{prefix}{fact.fact_id}" for fact in source_facts}
    equation_label_spans = {
        fact.fact_id: span(fact.label_span) for fact in snapshot.equation_labels
    }
    equation_reference_role_spans = {
        fact.fact_id: span(fact.role_span) for fact in snapshot.equation_refs
    }
    equation_reference_target_spans = {
        fact.fact_id: span(fact.target_span) for fact in snapshot.equation_refs
    }
    for fact in snapshot.equation_labels:
        if fact.label_syntax_kind != "tex-label" or fact.source_block_id is None:
            continue
        source_block_id = fact_ids.get(
            fact.source_block_id,
            f"{prefix}{fact.source_block_id}",
        )
        assert fact.label_span is not None
        fact_ids[fact.fact_id] = f"{source_block_id}::label::{fact.label_span.start}"
    for fact in snapshot.equation_refs:
        if not fact.ref_kind.startswith("tex-") or fact.source_block_id is None:
            continue
        source_block_id = fact_ids.get(
            fact.source_block_id,
            f"{prefix}{fact.source_block_id}",
        )
        assert fact.target_span is not None
        fact_ids[fact.fact_id] = f"{source_block_id}::ref::{fact.target_span.start}"

    def remapped_fact_id(value: str) -> str:
        return fact_ids.get(value, f"{prefix}{value}")

    def optional_fact_id(value: str | None) -> str | None:
        if value is None:
            return None
        return remapped_fact_id(value)

    inline_occurrences: dict[tuple[str, str], int] = {}
    remapped_inline_math: list[InlineMathFact] = []
    for fact in snapshot.inline_math:
        accessibility_id = None
        if fact.delimiter_kind != "plain-text":
            identity = (fact.delimiter_kind, fact.body)
            occurrence = inline_occurrences.get(identity, 0)
            inline_occurrences[identity] = occurrence + 1
            accessibility_id = inline_math_accessibility_id(
                document.path.as_posix(),
                fact.delimiter_kind,
                fact.body,
                occurrence,
                notebook_cell=cell_index,
            )
        remapped_inline_math.append(
            replace(
                fact,
                fact_id=remapped_fact_id(fact.fact_id),
                document_id=document.path.as_posix(),
                span=span(fact.span),
                accessibility_id=accessibility_id,
            )
        )
    remapped_display_math = tuple(
        replace(
            fact,
            fact_id=remapped_fact_id(fact.fact_id),
            document_id=document.path.as_posix(),
            span=span(fact.span),
            label_fact_ids=tuple(remapped_fact_id(value) for value in fact.label_fact_ids),
        )
        for fact in snapshot.display_math
    )
    remapped_unknown_math = tuple(
        replace(
            fact,
            fact_id=remapped_fact_id(fact.fact_id),
            document_id=document.path.as_posix(),
            span=span(fact.span),
            source_math_fact_id=remapped_fact_id(fact.source_math_fact_id),
        )
        for fact in snapshot.unknown_math
    )
    remapped_generated_formulas = tuple(
        replace(
            fact,
            fact_id=remapped_fact_id(fact.fact_id),
            document_id=document.path.as_posix(),
            span=span(fact.span),
            source_math_fact_id=optional_fact_id(fact.source_math_fact_id),
        )
        for fact in snapshot.generated_formulas
    )
    remapped_anchors = tuple(
        replace(
            anchor,
            fact_id=remapped_fact_id(anchor.fact_id),
            document_id=document.path.as_posix(),
            span=span(anchor.span),
            label_span=span(anchor.label_span),
            attaches_to_fact_id=optional_fact_id(anchor.attaches_to_fact_id),
        )
        for anchor in snapshot.target_anchors
    )
    remapped_generic_refs = tuple(
        replace(
            reference,
            fact_id=remapped_fact_id(reference.fact_id),
            document_id=document.path.as_posix(),
            span=span(reference.span),
            role_span=span(reference.role_span),
            target_span=span(reference.target_span),
        )
        for reference in snapshot.generic_refs
    )
    remapped_equation_labels: list[EquationLabelFact] = []
    for label in snapshot.equation_labels:
        label_span = equation_label_spans[label.fact_id]
        remapped_equation_labels.append(
            replace(
                label,
                fact_id=remapped_fact_id(label.fact_id),
                document_id=document.path.as_posix(),
                span=label_span if label.span == label.label_span else span(label.span),
                label_span=label_span,
                source_block_id=optional_fact_id(label.source_block_id),
            )
        )
    remapped_equation_refs: list[EquationRefFact] = []
    for reference in snapshot.equation_refs:
        role_span = equation_reference_role_spans[reference.fact_id]
        remapped_equation_refs.append(
            replace(
                reference,
                fact_id=remapped_fact_id(reference.fact_id),
                document_id=document.path.as_posix(),
                span=role_span if reference.span == reference.role_span else span(reference.span),
                target_span=equation_reference_target_spans[reference.fact_id],
                role_span=role_span,
                source_block_id=optional_fact_id(reference.source_block_id),
            )
        )
    remapped_crossrefs = tuple(
        replace(
            metadata,
            fact_id=remapped_fact_id(metadata.fact_id),
            document_id=document.path.as_posix(),
            span=span(metadata.span),
            source_fact_id=remapped_fact_id(metadata.source_fact_id),
            output_boundary=f"{document.path.as_posix()}#cell-{cell_index}",
            target_span=span(metadata.target_span),
        )
        for metadata in snapshot.crossref_metadata
    )
    return FactSnapshot(
        inline_math=tuple(remapped_inline_math),
        display_math=remapped_display_math,
        unknown_math=remapped_unknown_math,
        target_anchors=remapped_anchors,
        generic_refs=remapped_generic_refs,
        equation_labels=tuple(remapped_equation_labels),
        equation_refs=tuple(remapped_equation_refs),
        crossref_metadata=remapped_crossrefs,
        generated_formulas=remapped_generated_formulas,
    )
