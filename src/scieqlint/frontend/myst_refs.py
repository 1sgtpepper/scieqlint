"""Reference fact lowering for Markdown links and MyST roles."""

from __future__ import annotations

import re
from collections.abc import Sequence

from scieqlint.facts.reference import EquationRefFact, GenericRefFact
from scieqlint.io.source import SourceDocument
from scieqlint.source.maps import SourceMap

from .myst_shared import (
    ROLE_RE,
    MarkdownLinkToken,
    OffsetRange,
    extract_role_target_and_title,
    in_ranges,
    inline_code_ranges,
    is_escaped,
    markdown_link_metadata_ranges,
    markdown_link_tokens,
    normalize_label,
)


def scan_refs(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
) -> tuple[tuple[GenericRefFact, ...], tuple[EquationRefFact, ...]]:
    generic: list[GenericRefFact] = []
    equation: list[EquationRefFact] = []
    occupied_with_code = (*tuple(occupied), *inline_code_ranges(document))
    link_metadata = markdown_link_metadata_ranges(document.text)
    for token in markdown_link_tokens(document.text):
        if token.is_image or in_ranges(token.start, occupied_with_code):
            continue
        if (
            token.destination_start == token.destination_end
            or document.text[token.destination_start] != "#"
        ):
            continue
        generic.append(_markdown_link_ref_fact(document, smap, token))
    for match in ROLE_RE.finditer(document.text):
        if (
            in_ranges(match.start(), occupied_with_code)
            or in_ranges(match.start(), link_metadata)
            or is_escaped(document.text, match.start())
        ):
            continue
        role = match.group("role")
        body = match.group("body")
        target, title = extract_role_target_and_title(body)
        if not target:
            continue
        target_start = match.start("body") + body.rfind(target)
        if role == "ref":
            generic.append(
                _generic_role_ref_fact(document, smap, match, target, title, target_start)
            )
        else:
            equation.append(
                _equation_role_ref_fact(document, smap, match, role, target, target_start)
            )
    return tuple(generic), tuple(equation)


def _markdown_link_ref_fact(
    document: SourceDocument,
    smap: SourceMap,
    token: MarkdownLinkToken,
) -> GenericRefFact:
    target_start = token.destination_start + 1
    target = document.text[target_start : token.destination_end]
    return GenericRefFact(
        fact_id=f"{document.path.as_posix()}::md-ref::{target_start}",
        document_id=document.path.as_posix(),
        span=smap.span(token.start, token.end),
        raw=document.text[token.start : token.end],
        role_kind="markdown-link",
        target=target,
        normalized_target=normalize_label(target),
        role_span=smap.span(token.start, token.end),
        target_span=smap.span(target_start, token.destination_end),
    )


def _generic_role_ref_fact(
    document: SourceDocument,
    smap: SourceMap,
    match: re.Match[str],
    target: str,
    title: str | None,
    target_start: int,
) -> GenericRefFact:
    return GenericRefFact(
        fact_id=f"{document.path.as_posix()}::ref::{target_start}",
        document_id=document.path.as_posix(),
        span=smap.span(match.start(), match.end()),
        raw=match.group(0),
        role_kind="ref",
        target=target,
        normalized_target=normalize_label(target),
        title=title,
        role_span=smap.span(match.start(), match.end()),
        target_span=smap.span(target_start, target_start + len(target)),
    )


def _equation_role_ref_fact(
    document: SourceDocument,
    smap: SourceMap,
    match: re.Match[str],
    role: str,
    target: str,
    target_start: int,
) -> EquationRefFact:
    return EquationRefFact(
        fact_id=f"{document.path.as_posix()}::eq-ref::{target_start}",
        document_id=document.path.as_posix(),
        span=smap.span(match.start(), match.end()),
        raw=match.group(0),
        ref_kind=role,
        target=target,
        normalized_target=normalize_label(target),
        role_span=smap.span(match.start(), match.end()),
        target_span=smap.span(target_start, target_start + len(target)),
    )
