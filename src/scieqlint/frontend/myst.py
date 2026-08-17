"""MyST/Markdown source lowering for structure, references, and math facts.

This is deliberately a conservative line-oriented frontend. It is not a full
replacement for MyST's parser. It produces facts with stable source spans;
semantic diagnostics remain owned by engines.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.io.source import SourceDocument
from scieqlint.markdown import (
    code_fence_ranges,
    inline_code_ranges,
    markdown_reference_snapshot,
)
from scieqlint.source.maps import SourceMap

from .crossref import crossref_metadata_facts
from .generated import (
    scan_bracketed_latex_blocks,
    scan_equation_like_text_items,
    scan_formula_candidates,
    scan_formula_placeholders,
)
from .myst_blocks import (
    directive_and_code_cell_facts,
    directive_option_prefix_lines,
    myst_options,
    quarto_options,
    scan_fences,
    scan_structure_syntax_issues,
)
from .myst_headings import (
    attach_anchors,
    is_immediate_attachment,
    scan_anchors,
    scan_heading_syntax_issues,
    scan_headings,
    sections_for_headings,
)
from .myst_math import (
    math_occupied_ranges,
    scan_display_math,
    scan_inline_math,
    scan_raw_latex_math,
)
from .myst_refs import scan_refs
from .myst_shared import dollar_display_ranges, line_ranges

_directive_option_prefix_lines = directive_option_prefix_lines
_myst_options = myst_options
_quarto_options = quarto_options
_is_immediate_attachment = is_immediate_attachment


class MySTFrontend:
    """Lower source documents into a ``FactSnapshot`` without diagnostics."""

    def lower(self, documents: Sequence[SourceDocument]) -> FactSnapshot:
        parts = tuple(_lower_document(document) for document in documents)
        return FactSnapshot(
            documents=tuple(documents),
            headings=_flatten(parts, "headings"),
            sections=_flatten(parts, "sections"),
            fences=_flatten(parts, "fences"),
            directives=_flatten(parts, "directives"),
            code_cells=_flatten(parts, "code_cells"),
            structure_syntax_issues=_flatten(parts, "structure_syntax_issues"),
            target_anchors=_flatten(parts, "target_anchors"),
            generic_refs=_flatten(parts, "generic_refs"),
            equation_labels=_flatten(parts, "equation_labels"),
            equation_refs=_flatten(parts, "equation_refs"),
            crossref_metadata=_flatten(parts, "crossref_metadata"),
            inline_math=_flatten(parts, "inline_math"),
            display_math=_flatten(parts, "display_math"),
            unknown_math=_flatten(parts, "unknown_math"),
            generated_formulas=_flatten(parts, "generated_formulas"),
        )


def _flatten(parts: Sequence[FactSnapshot], name: str) -> tuple[Any, ...]:
    items: list[Any] = []
    for part in parts:
        items.extend(getattr(part, name))
    return tuple(items)


def _lower_document(document: SourceDocument) -> FactSnapshot:
    smap = SourceMap.for_document(document)
    lines = line_ranges(document.text)
    reference_snapshot = markdown_reference_snapshot(document.text)
    live_fence_ranges = code_fence_ranges(
        document.text,
        reference_snapshot.link_metadata_ranges,
    )
    fences = scan_fences(document, smap, lines, live_fence_ranges)
    occupied_structure_ranges = reference_snapshot.opaque_ranges
    directives, code_cells = directive_and_code_cell_facts(document, fences)
    structure_syntax_issues = (
        *scan_structure_syntax_issues(document, smap, occupied_structure_ranges, fences),
        *scan_heading_syntax_issues(document, smap, lines, occupied_structure_ranges),
    )
    headings = tuple(scan_headings(document, smap, lines, occupied_structure_ranges))
    anchors = tuple(scan_anchors(document, smap, lines, occupied_structure_ranges))
    target_anchors = tuple(attach_anchors(document, anchors, headings, fences))
    sections = tuple(sections_for_headings(headings))
    dollar_displays = dollar_display_ranges(
        document.text,
        reference_snapshot.link_metadata_ranges,
    )
    display_math, equation_labels, display_equation_refs = scan_display_math(
        document,
        smap,
        fences,
        dollar_displays,
    )
    raw_display_math, raw_labels, raw_refs, unknown_math = scan_raw_latex_math(
        document,
        smap,
        (
            *reference_snapshot.opaque_ranges,
            *math_occupied_ranges(display_math),
            *live_fence_ranges,
            *inline_code_ranges(document.text),
        ),
    )
    # Preserve the established fence-then-dollar fact ordering; raw-LaTeX facts
    # extend that contract without reordering pre-existing buckets.
    display_math = (*display_math, *raw_display_math)
    equation_labels = (*equation_labels, *raw_labels)
    generic_refs, prose_equation_refs = scan_refs(document, smap, reference_snapshot)
    equation_refs = tuple(
        sorted(
            (*display_equation_refs, *raw_refs, *prose_equation_refs),
            key=lambda fact: (
                fact.span.start if fact.span is not None else -1,
                fact.fact_id,
            ),
        )
    )
    crossref_metadata = crossref_metadata_facts(document, generic_refs, equation_refs)
    inline_math = tuple(
        scan_inline_math(
            document,
            smap,
            (*math_occupied_ranges(display_math), *reference_snapshot.link_metadata_ranges),
            (
                *reference_snapshot.opaque_ranges,
                *((token.start, token.end) for token in reference_snapshot.links),
            ),
        )
    )
    generated_formulas = scan_formula_candidates(
        document,
        inline_math,
        display_math,
    )
    bracketed_blocks = scan_bracketed_latex_blocks(
        document,
        smap,
        (
            *reference_snapshot.opaque_ranges,
            *math_occupied_ranges(display_math),
            *((fact.span.start, fact.span.end) for fact in inline_math if fact.span is not None),
        ),
    )
    placeholders = scan_formula_placeholders(
        document,
        smap,
        inline_math,
        display_math,
        dollar_displays,
        reference_snapshot.links,
        reference_snapshot.opaque_ranges,
        (*live_fence_ranges, *inline_code_ranges(document.text)),
    )
    equation_like_text = scan_equation_like_text_items(
        document,
        smap,
        inline_math,
        tuple(
            (fact.span.start, fact.span.end)
            for fact in (*bracketed_blocks, *placeholders)
            if fact.span is not None
        ),
    )
    generated_formulas = tuple(
        sorted(
            (*generated_formulas, *bracketed_blocks, *placeholders, *equation_like_text),
            key=lambda fact: (
                fact.span.start if fact.span is not None else -1,
                fact.fact_id,
            ),
        )
    )
    return FactSnapshot(
        documents=(document,),
        headings=headings,
        sections=sections,
        fences=fences,
        directives=directives,
        code_cells=code_cells,
        structure_syntax_issues=structure_syntax_issues,
        target_anchors=target_anchors,
        generic_refs=generic_refs,
        equation_labels=equation_labels,
        equation_refs=equation_refs,
        crossref_metadata=crossref_metadata,
        inline_math=inline_math,
        display_math=display_math,
        unknown_math=unknown_math,
        generated_formulas=generated_formulas,
    )
