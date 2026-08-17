"""Lower MathHost macro-scope records into immutable fact buckets."""

from __future__ import annotations

from collections.abc import Sequence

from scieqlint.facts.math import (
    InlineMathFact,
    MathMacroDeclarationFact,
    MathMacroUseFact,
)
from scieqlint.io.source import SourceDocument
from scieqlint.parse.macros import (
    InlineMacroSource,
    MacroDeclarationKey,
    scan_scoped_inline_macros,
)
from scieqlint.source.maps import SourceMap


def inline_math_macro_facts(
    documents: Sequence[SourceDocument],
    inline_math: Sequence[InlineMathFact],
) -> tuple[tuple[MathMacroDeclarationFact, ...], tuple[MathMacroUseFact, ...]]:
    """Build facts from MathHost's document-scoped source-order model."""

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
        if document.text[fact.span.start : fact.span.end] != fact.body:
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
                span=source_maps[fact.document_id].span(
                    fact.span.start + syntax.name_start,
                    fact.span.start + syntax.name_end,
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
                span=source_maps[fact.document_id].span(
                    fact.span.start + syntax.start,
                    fact.span.start + syntax.end,
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
