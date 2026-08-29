"""Persistent macro facts from bounded inline-TeX scope records."""

from __future__ import annotations

import json
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import replace

from scieqlint.diag.model import SourceSegment, SourceSpan
from scieqlint.facts.math import (
    InlineMathFact,
    MathMacroDeclarationFact,
    MathMacroUseFact,
)
from scieqlint.io.source import SourceDocument
from scieqlint.source.maps import SourceMap

from .macros import InlineMacroSource, MacroDeclarationKey, scan_scoped_inline_macros
from .normalize import _splitline_starts


def inline_math_macro_facts(
    documents: Sequence[SourceDocument],
    inline_math: Sequence[InlineMathFact],
) -> tuple[tuple[MathMacroDeclarationFact, ...], tuple[MathMacroUseFact, ...]]:
    """Resolve macro declarations and uses after MathHost owns math candidates."""

    documents_by_id = {document.path.as_posix(): document for document in documents}
    source_maps = {
        document_id: SourceMap.for_document(document)
        for document_id, document in documents_by_id.items()
    }
    facts_by_id: dict[str, InlineMathFact] = {}
    sources: list[InlineMacroSource] = []
    for fact in inline_math:
        if (
            fact.delimiter_kind == "plain-text"
            or fact.confidence != "source"
            or fact.span is None
            or fact.document_id not in documents_by_id
        ):
            continue
        document = documents_by_id[fact.document_id]
        segments = fact.span.segments
        if not segments:
            if document.text[fact.span.start : fact.span.end] != fact.body:
                continue
        else:
            if (
                fact.span.start != segments[0].start
                or fact.span.end != segments[-1].end
                or not _mapped_notebook_body_matches(document, segments, fact.body)
            ):
                continue
        facts_by_id[fact.fact_id] = fact
        sources.append(
            InlineMacroSource(
                document_id=fact.document_id,
                source_fact_id=fact.fact_id,
                source_start=fact.span.start,
                body=fact.body,
            )
        )

    scoped = scan_scoped_inline_macros(tuple(sources))
    line_starts_by_fact_id: dict[str, tuple[int, ...]] = {}

    def line_starts(fact: InlineMathFact) -> tuple[int, ...]:
        assert fact.span is not None
        if fact.span.cell_line is None:
            return ()
        starts = line_starts_by_fact_id.get(fact.fact_id)
        if starts is None:
            starts = _splitline_starts(fact.body)
            line_starts_by_fact_id[fact.fact_id] = starts
        return starts

    declarations: list[MathMacroDeclarationFact] = []
    declaration_ids: dict[MacroDeclarationKey, str] = {}
    for item in scoped.declarations:
        fact = facts_by_id[item.source.source_fact_id]
        assert fact.span is not None
        syntax = item.declaration
        fact_id = f"{fact.fact_id}::macro-declaration::{syntax.start}"
        declaration_ids[MacroDeclarationKey(fact.fact_id, syntax.start)] = fact_id
        declarations.append(
            MathMacroDeclarationFact(
                fact_id=fact_id,
                document_id=fact.document_id,
                span=_inline_macro_span(
                    fact,
                    source_maps[fact.document_id],
                    syntax.name_start,
                    syntax.name_end,
                    line_starts(fact),
                ),
                raw=fact.body[syntax.start : syntax.end],
                source_math_fact_id=fact.fact_id,
                macro_name=syntax.name,
                declaration_kind=syntax.declaration_kind,
                parameter_count=syntax.parameter_count,
                replacement=syntax.replacement,
                declaration_order=item.declaration_order,
            )
        )

    uses: list[MathMacroUseFact] = []
    for item in scoped.uses:
        fact = facts_by_id[item.source.source_fact_id]
        assert fact.span is not None
        syntax = item.use
        uses.append(
            MathMacroUseFact(
                fact_id=f"{fact.fact_id}::macro-use::{syntax.start}",
                document_id=fact.document_id,
                span=_inline_macro_span(
                    fact,
                    source_maps[fact.document_id],
                    syntax.start,
                    syntax.end,
                    line_starts(fact),
                ),
                raw=fact.body[syntax.start : syntax.end],
                source_math_fact_id=fact.fact_id,
                macro_name=syntax.name,
                active_declaration_fact_id=(
                    declaration_ids[item.active_declaration]
                    if item.active_declaration is not None
                    else None
                ),
            )
        )
    return tuple(declarations), tuple(uses)


def _mapped_notebook_body_matches(
    document: SourceDocument,
    segments: Sequence[SourceSegment],
    body: str,
) -> bool:
    """Validate mapped logical characters against their raw notebook ranges."""

    if len(segments) != len(body):
        return False
    previous_end = -1
    for segment, expected in zip(segments, body, strict=True):
        raw_parts: list[str] = []
        for range_start, range_end in segment.ranges:
            if range_start < previous_end or range_start < 0 or range_end > len(document.text):
                return False
            raw_parts.append(document.text[range_start:range_end])
            previous_end = range_end
        raw = "".join(raw_parts)
        if len(raw) == 1 and raw not in {'"', "\\"} and ord(raw) >= 0x20:
            decoded = raw
        else:
            try:
                decoded = json.loads(f'"{raw}"')
            except json.JSONDecodeError:
                return False
        normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
        if normalized != expected:
            return False
    return True


def _inline_macro_span(
    fact: InlineMathFact,
    source_map: SourceMap,
    start: int,
    end: int,
    line_starts: tuple[int, ...],
) -> SourceSpan:
    assert fact.span is not None
    if start < 0 or end <= start or end > len(fact.body):
        raise ValueError("inline macro subspan is outside its source text")
    cell_line = (
        None
        if fact.span.cell_line is None
        else fact.span.cell_line + bisect_right(line_starts, start) - 1
    )
    if fact.span.segments:
        if len(fact.span.segments) != len(fact.body):
            raise ValueError("inline macro source mapping does not match its source text")
        segments = fact.span.segments[start:end]
        first = segments[0]
        last = segments[-1]
        return replace(
            fact.span,
            start=first.start,
            end=last.end,
            line=first.line,
            col=first.col,
            end_line=last.end_line,
            end_col=last.end_col,
            cell_line=cell_line,
            segments=segments,
        )
    span = source_map.span(fact.span.start + start, fact.span.start + end)
    return replace(
        span,
        cell=fact.span.cell,
        cell_line=cell_line,
    )
