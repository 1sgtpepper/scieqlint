"""LaTeX symbol-directive extraction."""

from __future__ import annotations

from scieqlint.diag.model import Diagnostic
from scieqlint.io.source import SourceDocument
from scieqlint.scan.base import SymbolDirective, SymbolDirectiveSource
from scieqlint.scan.latex_support import (
    comment_start_index,
    diagnostic_key,
    in_ranges,
    line_ranges,
    span,
)
from scieqlint.scan.symbols import parse_symbol_directive

SYMBOL_PREFIX = "scieqlint-symbol:"


def symbol_directives(
    document: SourceDocument,
    verbatim: tuple[tuple[int, int], ...],
) -> tuple[tuple[SymbolDirective, ...], tuple[Diagnostic, ...]]:
    directives: list[SymbolDirective] = []
    diagnostics: list[Diagnostic] = []
    for line_start, line_end in line_ranges(document.text):
        comment_start = comment_start_index(document.text[line_start:line_end])
        if comment_start is None:
            continue
        start = line_start + comment_start
        if in_ranges(start, verbatim):
            continue
        comment = document.text[start:line_end].rstrip("\n")
        comment_body = comment[1:].lstrip()
        if not comment_body.startswith(SYMBOL_PREFIX):
            continue
        body_start = start + 1 + len(comment[1:]) - len(comment_body) + len(SYMBOL_PREFIX)
        directive, diagnostic = parse_symbol_directive(
            body=document.text[body_start:line_end],
            raw=comment,
            span=span(document, start, line_end),
            source=SymbolDirectiveSource.LATEX_COMMENT,
            make_span=lambda span_start, span_end: span(document, span_start, span_end),
            body_start=body_start,
        )
        if directive is not None:
            directives.append(directive)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return (
        tuple(sorted(directives, key=lambda directive: directive.span.start)),
        tuple(sorted(diagnostics, key=diagnostic_key)),
    )
