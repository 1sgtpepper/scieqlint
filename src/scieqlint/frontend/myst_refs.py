"""Reference fact lowering for Markdown links and MyST roles."""

from __future__ import annotations

import re

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.reference import EquationRefFact, GenericRefFact
from scieqlint.io.source import SourceDocument
from scieqlint.io.workspace import WorkspaceHost
from scieqlint.markdown import (
    MarkdownLinkToken,
    MarkdownReferenceSnapshot,
    is_escaped,
)
from scieqlint.source.maps import SourceMap

from .myst_shared import (
    ROLE_RE,
    extract_role_target_and_title,
    in_ranges,
    normalize_label,
)


def scan_refs(
    document: SourceDocument,
    smap: SourceMap,
    snapshot: MarkdownReferenceSnapshot,
    *,
    workspace: WorkspaceHost,
) -> tuple[tuple[GenericRefFact, ...], tuple[EquationRefFact, ...]]:
    generic: list[GenericRefFact] = []
    equation: list[EquationRefFact] = []
    occupied = snapshot.opaque_ranges
    link_tokens = snapshot.links
    for token in link_tokens:
        if token.is_image or token.destination is None:
            continue
        if (
            token.fragment_target is None
            and workspace.project_reference_target(document.path, token.destination) is None
        ):
            continue
        generic.append(_markdown_link_ref_fact(document, smap, token, workspace=workspace))
    for match in ROLE_RE.finditer(document.text):
        if in_ranges(match.start(), occupied) or is_escaped(document.text, match.start()):
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
                _equation_role_ref_fact(document, smap, match, role, target, title, target_start)
            )
    return tuple(generic), tuple(equation)


def _markdown_link_ref_fact(
    document: SourceDocument,
    smap: SourceMap,
    token: MarkdownLinkToken,
    *,
    workspace: WorkspaceHost,
) -> GenericRefFact:
    assert token.destination is not None
    assert token.destination_start is not None
    assert token.destination_end is not None
    project_target = workspace.project_reference_target(document.path, token.destination)
    assert token.label_start is not None
    assert token.label_end is not None
    label_text = document.text[token.label_start : token.label_end].strip()
    title = label_text or None
    title_span = None
    if title is not None:
        title_offset = document.text.find(title, token.label_start, token.label_end)
        title_span = smap.span(title_offset, title_offset + len(title))
    fragment = token.fragment_target
    if project_target is not None:
        fragment = project_target.fragment
    source_member = (
        workspace.normalize_project_path(document.path)
        if project_target is None and fragment is not None
        else None
    )
    if fragment is not None:
        if token.fragment_target is not None:
            assert token.fragment_target_start is not None
            target_start = token.fragment_target_start
        else:
            target_start = token.destination_start
        target = fragment
    else:
        target_start = token.destination_start
        target = token.destination
    return GenericRefFact(
        fact_id=f"{document.path.as_posix()}::md-ref::{target_start}",
        document_id=document.path.as_posix(),
        span=smap.span(token.start, token.end),
        raw=document.text[token.start : token.end],
        role_kind="markdown-link",
        target=target,
        normalized_target=normalize_label(target),
        title=title,
        title_span=title_span,
        role_span=smap.span(token.start, token.end),
        target_span=smap.span(token.destination_start, token.destination_end),
        raw_target_path=None if project_target is None else project_target.raw_path,
        resolved_raw_target_path=(
            None if project_target is None else project_target.resolved_raw_path
        ),
        normalized_target_path=(
            project_target.normalized_path if project_target is not None else source_member
        ),
        target_fragment=fragment,
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
        title_span=_role_title_span(smap, match, title),
        role_span=smap.span(match.start(), match.end()),
        target_span=smap.span(target_start, target_start + len(target)),
    )


def _equation_role_ref_fact(
    document: SourceDocument,
    smap: SourceMap,
    match: re.Match[str],
    role: str,
    target: str,
    title: str | None,
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
        title=title,
        title_span=_role_title_span(smap, match, title),
        role_span=smap.span(match.start(), match.end()),
        target_span=smap.span(target_start, target_start + len(target)),
    )


def _role_title_span(
    smap: SourceMap,
    match: re.Match[str],
    title: str | None,
) -> SourceSpan | None:
    if title is None:
        return None
    body = match.group("body")
    relative_start = body.find(title)
    if relative_start < 0:
        return None
    start = match.start("body") + relative_start
    return smap.span(start, start + len(title))
