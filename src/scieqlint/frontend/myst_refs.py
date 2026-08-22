"""Reference fact lowering for Markdown links and MyST roles."""

from __future__ import annotations

import re
from collections.abc import Sequence

from scieqlint.facts.reference import EquationRefFact, GenericRefFact
from scieqlint.io.source import SourceDocument
from scieqlint.markdown import (
    MarkdownLinkToken,
    MarkdownReferenceSnapshot,
    is_escaped,
)
from scieqlint.source.maps import SourceMap

from .myst_shared import (
    ROLE_RE,
    OffsetRange,
    extract_role_target_and_title,
    in_ranges,
    normalize_label,
)


def scan_refs(
    document: SourceDocument,
    smap: SourceMap,
    snapshot: MarkdownReferenceSnapshot,
    *,
    raw_occupied: Sequence[OffsetRange] = (),
) -> tuple[tuple[GenericRefFact, ...], tuple[EquationRefFact, ...]]:
    generic: list[GenericRefFact] = []
    equation: list[EquationRefFact] = []
    occupied = snapshot.opaque_ranges
    link_tokens = snapshot.links
    for token in link_tokens:
        if token.is_image or token.destination is None or in_ranges(token.start, raw_occupied):
            continue
        if token.fragment_target is None:
            continue
        generic.append(_markdown_link_ref_fact(document, smap, token))
    for match in ROLE_RE.finditer(document.text):
        if (
            in_ranges(match.start(), occupied)
            or in_ranges(match.start(), raw_occupied)
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
    assert token.fragment_target is not None
    assert token.fragment_target_start is not None
    assert token.fragment_target_end is not None
    target_start = token.fragment_target_start
    target = token.fragment_target
    return GenericRefFact(
        fact_id=f"{document.path.as_posix()}::md-ref::{target_start}",
        document_id=document.path.as_posix(),
        span=smap.span(token.start, token.end),
        raw=document.text[token.start : token.end],
        role_kind="markdown-link",
        target=target,
        normalized_target=normalize_label(target),
        role_span=smap.span(token.start, token.end),
        target_span=smap.span(target_start, token.fragment_target_end),
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
