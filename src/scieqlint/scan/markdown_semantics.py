"""Markdown math labels, references, symbols, and source-span helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.io.source import SourceDocument
from scieqlint.scan.base import (
    EquationLabel,
    EquationReference,
    LabelSource,
    MathBlock,
    MathContainer,
    ReferenceSource,
    SymbolDirective,
    SymbolDirectiveSource,
)
from scieqlint.scan.symbols import parse_symbol_directive

TEX_LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")
DOLLAR_LABEL_RE = re.compile(r"\{#([^}\s]+)\}|\(([^()\s]+)\)")
MYST_LABEL_RE = re.compile(r"^[ \t]*:label:[ \t]*(?P<label>\S+)[ \t]*$", re.MULTILINE)
MD_LINK_RE = re.compile(r"\[[^\]]*]\(#(?P<target>[^)\s]+)\)")
EQ_ROLE_RE = re.compile(r"\{(?P<role>eq|numref)\}`(?P<body>[^`]+)`")
SYMBOL_DIRECTIVE_RE = re.compile(
    r"<!--\s*scieqlint-symbol:\s*(?P<body>.*?)\s*-->",
    re.DOTALL,
)


def tex_labels(document: SourceDocument, block: MathBlock) -> Iterable[EquationLabel]:
    for match in TEX_LABEL_RE.finditer(block.text):
        label_start = block.span.start + match.start(1)
        label_end = block.span.start + match.end(1)
        yield EquationLabel(
            label=normalize_label(match.group(1)),
            span=span(document, label_start, label_end),
            block_id=block.block_id,
            source=LabelSource.TEX_LABEL_IN_MARKDOWN_MATH,
        )


def display_tail_labels(document: SourceDocument, block: MathBlock) -> Iterable[EquationLabel]:
    close_start = document.text.find("$$", block.span.end)
    if close_start == -1:
        return
    tail_start = close_start + 2
    line_end = document.text.find("\n", tail_start)
    if line_end == -1:
        line_end = len(document.text)
    tail = document.text[tail_start:line_end]
    for match in DOLLAR_LABEL_RE.finditer(tail):
        raw = match.group(1) or match.group(2)
        if raw is None:
            continue
        label_start = tail_start + match.start(1 if match.group(1) else 2)
        label_end = tail_start + match.end(1 if match.group(1) else 2)
        yield EquationLabel(
            label=normalize_label(raw),
            span=span(document, label_start, label_end),
            block_id=block.block_id,
            source=(
                LabelSource.MYST_DOLLAR_LABEL if match.group(2) else LabelSource.MARKDOWN_ANCHOR
            ),
        )


def myst_directive_labels(document: SourceDocument, block: MathBlock) -> Iterable[EquationLabel]:
    for match in MYST_LABEL_RE.finditer(block.text):
        label_start = block.span.start + match.start("label")
        label_end = block.span.start + match.end("label")
        yield EquationLabel(
            label=normalize_label(match.group("label")),
            span=span(document, label_start, label_end),
            block_id=block.block_id,
            source=LabelSource.MYST_DIRECTIVE_LABEL,
        )


def references(document: SourceDocument) -> Iterable[EquationReference]:
    for match in MD_LINK_RE.finditer(document.text):
        target = normalize_label(match.group("target"))
        yield EquationReference(
            target=target,
            span=span(document, match.start("target"), match.end("target")),
            raw=match.group(0),
            source=ReferenceSource.MARKDOWN_ANCHOR,
        )
    for match in EQ_ROLE_RE.finditer(document.text):
        role = match.group("role")
        body = match.group("body")
        target = _extract_role_target(body)
        source = ReferenceSource.MYST_EQ_ROLE if role == "eq" else ReferenceSource.MYST_NUMREF_ROLE
        target_start = match.start("body") + body.rfind(target)
        yield EquationReference(
            target=normalize_label(target),
            span=span(document, target_start, target_start + len(target)),
            raw=match.group(0),
            source=source,
        )


def symbol_directives(
    document: SourceDocument,
    occupied: tuple[tuple[int, int], ...],
) -> tuple[tuple[SymbolDirective, ...], tuple[Diagnostic, ...]]:
    directives: list[SymbolDirective] = []
    diagnostics: list[Diagnostic] = []
    for match in SYMBOL_DIRECTIVE_RE.finditer(document.text):
        if in_ranges(match.start(), occupied):
            continue
        directive, diagnostic = parse_symbol_directive(
            body=match.group("body"),
            raw=match.group(0),
            span=span(document, match.start(), match.end()),
            source=SymbolDirectiveSource.MARKDOWN_COMMENT,
            make_span=lambda start, end: span(document, start, end),
            body_start=match.start("body"),
        )
        if directive is not None:
            directives.append(directive)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return (
        tuple(sorted(directives, key=lambda directive: directive.span.start)),
        tuple(sorted(diagnostics, key=diagnostic_key)),
    )


def in_ranges(position: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= position < end for start, end in ranges)


def normalize_label(value: str) -> str:
    value = value.strip()
    return value[1:] if value.startswith("#") else value


def block_id(
    document: SourceDocument,
    span_value: SourceSpan,
    container: MathContainer,
) -> str:
    return f"{document.display_path}:{span_value.line}:{span_value.col}:{container.value}"


def span(document: SourceDocument, start: int, end: int) -> SourceSpan:
    line, col = document.line_index.position(start)
    end_line, end_col = document.line_index.position(max(start, end - 1))
    return SourceSpan(
        path=document.path,
        start=start,
        end=end,
        line=line,
        col=col,
        end_line=end_line,
        end_col=end_col,
    )


def scan_diagnostic(document: SourceDocument, start: int, end: int) -> Diagnostic:
    info = CATALOG["SCAN001"]
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=info.message,
        span=span(document, start, end),
        rule="scanner",
    )


def diagnostic_key(diagnostic: Diagnostic) -> int:
    return diagnostic.span.start if diagnostic.span is not None else 0


def _extract_role_target(body: str) -> str:
    angle = re.search(r"<([^<>]+)>\s*$", body)
    return angle.group(1).strip() if angle else body.strip()
