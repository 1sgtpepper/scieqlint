"""LaTeX labels and references extracted from scanned math blocks."""

from __future__ import annotations

import re
from collections.abc import Iterable

from scieqlint.io.source import SourceDocument
from scieqlint.scan.base import (
    EquationLabel,
    EquationReference,
    LabelSource,
    MathBlock,
    ReferenceSource,
)
from scieqlint.scan.latex_support import in_ranges, normalize_label, span

LABEL_RE = re.compile(r"\\label\{(?P<label>[^{}]+)\}")
REFERENCE_RE = re.compile(r"\\(?P<kind>eqref|ref)\{(?P<target>[^{}]+)\}")


def labels(
    document: SourceDocument,
    blocks: list[MathBlock],
    ignored: tuple[tuple[int, int], ...],
) -> Iterable[EquationLabel]:
    for block in blocks:
        source_text = document.text[block.span.start : block.span.end]
        for match in LABEL_RE.finditer(source_text):
            label_start = block.span.start + match.start("label")
            label_end = block.span.start + match.end("label")
            if in_ranges(match.start() + block.span.start, ignored):
                continue
            yield EquationLabel(
                label=normalize_label(match.group("label")),
                span=span(document, label_start, label_end),
                block_id=block.block_id,
                source=LabelSource.LATEX_LABEL,
            )


def references(
    document: SourceDocument,
    ignored: tuple[tuple[int, int], ...],
) -> Iterable[EquationReference]:
    for match in REFERENCE_RE.finditer(document.text):
        if in_ranges(match.start(), ignored):
            continue
        target = normalize_label(match.group("target"))
        source = (
            ReferenceSource.LATEX_EQREF
            if match.group("kind") == "eqref"
            else ReferenceSource.LATEX_REF
        )
        yield EquationReference(
            target=target,
            span=span(document, match.start("target"), match.end("target")),
            raw=match.group(0),
            source=source,
        )
