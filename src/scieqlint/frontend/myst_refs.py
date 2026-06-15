"""Reference fact lowering for Markdown links and MyST roles."""

from __future__ import annotations

import re
from collections.abc import Sequence

from scieqlint.facts.reference import EquationRefFact, GenericRefFact
from scieqlint.io.source import SourceDocument
from scieqlint.source.maps import SourceMap

from .myst_shared import (
    MD_LINK_RE,
    ROLE_RE,
    OffsetRange,
    extract_role_target_and_title,
    in_ranges,
    inline_code_ranges,
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
    for match in MD_LINK_RE.finditer(document.text):
        if in_ranges(match.start(), occupied_with_code):
            continue
        generic.append(_markdown_link_ref_fact(document, smap, match))
    for match in ROLE_RE.finditer(document.text):
        if in_ranges(match.start(), occupied_with_code):
            continue
        role = match.group("role")
        body = match.group("body")
        target, title = extract_role_target_and_title(body)
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
    match: re.Match[str],
) -> GenericRefFact:
    target = match.group("target")
    return GenericRefFact(
        fact_id=f"{document.path.as_posix()}::md-ref::{match.start('target')}",
        document_id=document.path.as_posix(),
        span=smap.span(match.start(), match.end()),
        raw=match.group(0),
        role_kind="markdown-link",
        target=target,
        normalized_target=normalize_label(target),
        role_span=smap.span(match.start(), match.end()),
        target_span=smap.span(match.start("target"), match.end("target")),
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
