"""Markdown and MyST scanner for the v0.1 subset."""

from __future__ import annotations

import re
from collections.abc import Iterable

from scieqlint.config.model import Config
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.io.source import SourceDocument
from scieqlint.scan.base import (
    EquationLabel,
    EquationReference,
    LabelSource,
    MathBlock,
    MathContainer,
    ReferenceSource,
    ScanResult,
)

DISPLAY_RE = re.compile(r"\$\$(?P<body>.*?)(?P<close>\$\$)(?P<tail>[^\n]*)", re.DOTALL)
FENCE_RE = re.compile(
    r"^```(?P<kind>math|\{math\})[ \t]*\n(?P<body>.*?)(?P<close>^```[ \t]*$)",
    re.MULTILINE | re.DOTALL,
)
TEX_LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")
DOLLAR_LABEL_RE = re.compile(r"\{#([^}\s]+)\}|\(([^()\s]+)\)")
MYST_LABEL_RE = re.compile(r"^[ \t]*:label:[ \t]*(?P<label>\S+)[ \t]*$", re.MULTILINE)
MD_LINK_RE = re.compile(r"\[[^\]]*]\(#(?P<target>[^)\s]+)\)")
EQ_ROLE_RE = re.compile(r"\{(?P<role>eq|numref)\}`(?P<body>[^`]+)`")


class MarkdownScanner:
    def scan(self, document: SourceDocument, config: Config) -> ScanResult:
        if not config.scanner.markdown:
            return ScanResult(blocks=())

        blocks: list[MathBlock] = []
        labels: list[EquationLabel] = []
        diagnostics: list[Diagnostic] = []

        for block in _display_blocks(document):
            blocks.append(block)
            labels.extend(_tex_labels(document, block))
            labels.extend(_display_tail_labels(document, block))

        if config.scanner.math_fences:
            for block in _fenced_blocks(document):
                blocks.append(block)
                labels.extend(_tex_labels(document, block))
                labels.extend(_myst_directive_labels(document, block))

        references = tuple(_references(document))
        return ScanResult(
            blocks=tuple(sorted(blocks, key=lambda block: block.span.start)),
            labels=tuple(sorted(labels, key=lambda label: label.span.start)),
            references=references,
            diagnostics=tuple(diagnostics),
        )


def _display_blocks(document: SourceDocument) -> Iterable[MathBlock]:
    for match in DISPLAY_RE.finditer(document.text):
        body = match.group("body")
        text = body.strip()
        body_start = match.start("body") + len(body) - len(body.lstrip())
        body_end = match.start("body") + len(body.rstrip())
        span = _span(document, body_start, body_end)
        yield MathBlock(
            text=text,
            span=span,
            block_id=_block_id(document, span, MathContainer.MARKDOWN_DISPLAY),
            container=MathContainer.MARKDOWN_DISPLAY,
        )


def _fenced_blocks(document: SourceDocument) -> Iterable[MathBlock]:
    for match in FENCE_RE.finditer(document.text):
        body = match.group("body")
        text = body.strip()
        body_start = match.start("body") + len(body) - len(body.lstrip())
        body_end = match.start("body") + len(body.rstrip())
        span = _span(document, body_start, body_end)
        yield MathBlock(
            text=text,
            span=span,
            block_id=_block_id(document, span, MathContainer.MARKDOWN_FENCE),
            container=MathContainer.MARKDOWN_FENCE,
        )


def _tex_labels(document: SourceDocument, block: MathBlock) -> Iterable[EquationLabel]:
    for match in TEX_LABEL_RE.finditer(block.text):
        label_start = block.span.start + match.start(1)
        label_end = block.span.start + match.end(1)
        yield EquationLabel(
            label=_normalize_label(match.group(1)),
            span=_span(document, label_start, label_end),
            block_id=block.block_id,
            source=LabelSource.TEX_LABEL_IN_MARKDOWN_MATH,
        )


def _display_tail_labels(document: SourceDocument, block: MathBlock) -> Iterable[EquationLabel]:
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
            label=_normalize_label(raw),
            span=_span(document, label_start, label_end),
            block_id=block.block_id,
            source=(
                LabelSource.MYST_DOLLAR_LABEL if match.group(2) else LabelSource.MARKDOWN_ANCHOR
            ),
        )


def _myst_directive_labels(document: SourceDocument, block: MathBlock) -> Iterable[EquationLabel]:
    for match in MYST_LABEL_RE.finditer(block.text):
        label_start = block.span.start + match.start("label")
        label_end = block.span.start + match.end("label")
        yield EquationLabel(
            label=_normalize_label(match.group("label")),
            span=_span(document, label_start, label_end),
            block_id=block.block_id,
            source=LabelSource.MYST_DIRECTIVE_LABEL,
        )


def _references(document: SourceDocument) -> Iterable[EquationReference]:
    for match in MD_LINK_RE.finditer(document.text):
        target = _normalize_label(match.group("target"))
        yield EquationReference(
            target=target,
            span=_span(document, match.start("target"), match.end("target")),
            raw=match.group(0),
            source=ReferenceSource.MARKDOWN_ANCHOR,
        )
    for match in EQ_ROLE_RE.finditer(document.text):
        role = match.group("role")
        body = match.group("body")
        target = _extract_role_target(body)
        source = (
            ReferenceSource.MYST_EQ_ROLE if role == "eq" else ReferenceSource.MYST_NUMREF_ROLE
        )
        target_start = match.start("body") + body.rfind(target)
        yield EquationReference(
            target=_normalize_label(target),
            span=_span(document, target_start, target_start + len(target)),
            raw=match.group(0),
            source=source,
        )


def _extract_role_target(body: str) -> str:
    angle = re.search(r"<([^<>]+)>\s*$", body)
    return angle.group(1).strip() if angle else body.strip()


def _normalize_label(value: str) -> str:
    value = value.strip()
    return value[1:] if value.startswith("#") else value


def _block_id(
    document: SourceDocument,
    span: SourceSpan,
    container: MathContainer,
) -> str:
    return f"{document.display_path}:{span.line}:{span.col}:{container.value}"


def _span(document: SourceDocument, start: int, end: int) -> SourceSpan:
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
