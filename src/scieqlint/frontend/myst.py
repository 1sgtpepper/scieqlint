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
from scieqlint.source.maps import SourceMap

from .myst_blocks import (
    directive_and_code_cell_facts,
    directive_option_prefix_lines,
    fence_ranges,
    myst_options,
    quarto_options,
    scan_fences,
    scan_structure_syntax_issues,
)
from .myst_headings import (
    attach_anchors,
    is_immediate_attachment,
    scan_anchors,
    scan_headings,
    sections_for_headings,
)
from .myst_math import math_occupied_ranges, scan_display_math, scan_inline_math
from .myst_refs import scan_refs
from .myst_shared import line_ranges

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
            inline_math=_flatten(parts, "inline_math"),
            display_math=_flatten(parts, "display_math"),
        )


def _flatten(parts: Sequence[FactSnapshot], name: str) -> tuple[Any, ...]:
    items: list[Any] = []
    for part in parts:
        items.extend(getattr(part, name))
    return tuple(items)


def _lower_document(document: SourceDocument) -> FactSnapshot:
    smap = SourceMap.for_document(document)
    lines = line_ranges(document.text)
    fences = scan_fences(document, smap, lines)
    occupied_fence_ranges = fence_ranges(fences, document.text)
    directives, code_cells = directive_and_code_cell_facts(document, fences)
    structure_syntax_issues = tuple(
        scan_structure_syntax_issues(document, smap, occupied_fence_ranges, fences)
    )
    headings = tuple(scan_headings(document, smap, lines, occupied_fence_ranges))
    anchors = tuple(scan_anchors(document, smap, lines, occupied_fence_ranges))
    target_anchors = tuple(attach_anchors(document, anchors, headings, fences))
    sections = tuple(sections_for_headings(headings))
    display_math, equation_labels = scan_display_math(
        document,
        smap,
        occupied_fence_ranges,
        fences,
    )
    generic_refs, equation_refs = scan_refs(document, smap, occupied_fence_ranges)
    inline_math = tuple(
        scan_inline_math(
            document,
            smap,
            math_occupied_ranges(occupied_fence_ranges, display_math),
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
        inline_math=inline_math,
        display_math=display_math,
    )
