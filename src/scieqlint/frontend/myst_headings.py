"""Heading, section, and target-anchor lowering for MyST/Markdown."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import replace

from scieqlint.facts.reference import TargetAnchorFact
from scieqlint.facts.structure import (
    FenceFact,
    HeadingFact,
    SectionFact,
    StructureSyntaxIssueFact,
)
from scieqlint.io.source import SourceDocument
from scieqlint.source.maps import SourceMap

from .myst_shared import (
    ANCHOR_RE,
    HEADING_RE,
    LineRange,
    OffsetRange,
    in_ranges,
    normalize_label,
    slug,
)


def scan_headings(
    document: SourceDocument,
    smap: SourceMap,
    lines: Sequence[LineRange],
    occupied: Sequence[OffsetRange],
) -> Iterable[HeadingFact]:
    for start, end, line in lines:
        if in_ranges(start, occupied):
            continue
        match = HEADING_RE.match(line)
        if match is None:
            continue

        hashes = match.group("hashes")
        body = match.group("body")
        space = match.group("space")
        if space is None and body:
            continue
        text = _heading_text(body)

        indent = len(line) - len(line.lstrip(" \t"))
        text_start = start + indent + len(hashes) + (len(space) if space else 0)
        yield HeadingFact(
            fact_id=f"{document.path.as_posix()}::heading::{start}",
            document_id=document.path.as_posix(),
            span=smap.span(start, end),
            raw=line,
            level=len(hashes),
            text=text,
            slug_candidate=slug(text),
            marker_span=smap.span(start + indent, start + indent + len(hashes)),
            text_span=smap.span(text_start, text_start + len(body.lstrip())) if body else None,
        )


def scan_heading_syntax_issues(
    document: SourceDocument,
    smap: SourceMap,
    lines: Sequence[LineRange],
    occupied: Sequence[OffsetRange],
) -> Iterable[StructureSyntaxIssueFact]:
    for start, _end, line in lines:
        if in_ranges(start, occupied):
            continue
        match = HEADING_RE.match(line)
        if match is None or match.group("space") is not None or not match.group("body"):
            continue
        yield StructureSyntaxIssueFact(
            fact_id=f"{document.path.as_posix()}::heading-issue::{start}",
            document_id=document.path.as_posix(),
            span=smap.span(
                start + len(line) - len(line.lstrip(" \t")),
                start + len(line) - len(line.lstrip(" \t")) + len(match.group("hashes")),
            ),
            raw=line,
            kind="atx-heading",
            reason="missing_space_after_atx_marker",
        )


def scan_anchors(
    document: SourceDocument,
    smap: SourceMap,
    lines: Sequence[LineRange],
    occupied: Sequence[OffsetRange],
) -> Iterable[TargetAnchorFact]:
    for start, end, line in lines:
        if in_ranges(start, occupied):
            continue
        match = ANCHOR_RE.match(line)
        if match is None:
            continue
        label = match.group("label")
        label_start = start + match.start("label")
        yield TargetAnchorFact(
            fact_id=f"{document.path.as_posix()}::anchor::{start}",
            document_id=document.path.as_posix(),
            span=smap.span(start, end),
            raw=line,
            label=label,
            normalized_label=normalize_label(label),
            target_kind=None,
            attaches_to_fact_id=None,
            placement="standalone",
            label_span=smap.span(label_start, label_start + len(label)),
        )


def attach_anchors(
    document: SourceDocument,
    anchors: Iterable[TargetAnchorFact],
    headings: Sequence[HeadingFact],
    fences: Sequence[FenceFact],
) -> Iterable[TargetAnchorFact]:
    attachable = sorted(
        (*headings, *fences),
        key=lambda fact: fact.span.start if fact.span else 0,
    )
    for anchor in anchors:
        next_fact = next(
            (
                fact
                for fact in attachable
                if fact.span is not None
                and anchor.span is not None
                and fact.span.start >= anchor.span.end
            ),
            None,
        )
        if next_fact is None or not is_immediate_attachment(document, anchor, next_fact):
            yield replace(anchor, placement="orphaned")
            continue
        kind = "heading" if isinstance(next_fact, HeadingFact) else "block"
        placement = "before_heading" if kind == "heading" else "before_block"
        yield replace(
            anchor,
            target_kind=kind,
            attaches_to_fact_id=next_fact.fact_id,
            placement=placement,
        )


def sections_for_headings(headings: Sequence[HeadingFact]) -> Iterable[SectionFact]:
    stack: list[tuple[int, str]] = []
    counters = [0] * 7
    for heading in headings:
        level = heading.level
        counters[level] += 1
        for idx in range(level + 1, 7):
            counters[idx] = 0
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else None
        fact_id = f"{heading.fact_id}::section"
        stack.append((level, fact_id))
        yield SectionFact(
            fact_id=fact_id,
            document_id=heading.document_id,
            span=heading.span,
            raw=heading.raw,
            heading_fact_id=heading.fact_id,
            parent_section_id=parent,
            depth=level,
            ordinal_path=tuple(counters[1 : level + 1]),
            starts_at=heading.span,
        )


def _heading_text(body: str) -> str:
    stripped = body.strip()
    return re.sub(r"[ \t]+#+[ \t]*$", "", stripped).strip()


def is_immediate_attachment(
    document: SourceDocument,
    anchor: TargetAnchorFact,
    next_fact: HeadingFact | FenceFact,
) -> bool:
    if anchor.span is None or next_fact.span is None:
        return False
    between = document.text[anchor.span.end : next_fact.span.start]
    for line in between.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("<!--"):
            return False
    return True
