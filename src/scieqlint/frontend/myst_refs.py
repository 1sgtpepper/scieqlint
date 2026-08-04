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

_MARKDOWN_LINK_RE = re.compile(
    r"(?P<image>!?)(?:\[(?P<label>(?:\\.|[^]\n])*)\]\((?P<body>[^)\n]*)\))"
)


def scan_refs(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
) -> tuple[tuple[GenericRefFact, ...], tuple[EquationRefFact, ...]]:
    generic: list[GenericRefFact] = []
    equation: list[EquationRefFact] = []
    occupied_with_code = (*tuple(occupied), *inline_code_ranges(document))
    link_metadata = _link_metadata_ranges(document.text)
    for match in MD_LINK_RE.finditer(document.text):
        if (
            in_ranges(match.start(), occupied_with_code)
            or in_ranges(match.start(), link_metadata)
            or _is_escaped(document.text, match.start())
            or (match.start() > 0 and document.text[match.start() - 1] == "!")
        ):
            continue
        generic.append(_markdown_link_ref_fact(document, smap, match))
    for match in ROLE_RE.finditer(document.text):
        if (
            in_ranges(match.start(), occupied_with_code)
            or in_ranges(match.start(), link_metadata)
            or _is_escaped(document.text, match.start())
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


def _link_metadata_ranges(text: str) -> tuple[OffsetRange, ...]:
    ranges: list[OffsetRange] = []
    for match in _MARKDOWN_LINK_RE.finditer(text):
        if match.group("image"):
            ranges.append((match.start(), match.end()))
        else:
            ranges.append((match.start("body"), match.end()))
    return tuple(ranges)


def _is_escaped(text: str, index: int) -> bool:
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return slash_count % 2 == 1


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
