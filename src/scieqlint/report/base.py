"""Reporter protocol."""

from __future__ import annotations

from typing import Protocol

from scieqlint.diag.model import CheckResult, SourceSpan


class Reporter(Protocol):
    def render(self, result: CheckResult) -> str: ...


def text_location(span: SourceSpan) -> str:
    if span.cell is None:
        return f"{span.path.as_posix()}:{span.line}:{span.col}"
    location = f"{span.path.as_posix()}#cell-{span.cell}"
    if span.cell_line is None:
        return location
    return f"{location}:{span.cell_line}:{span.col}"


def cell_location_prefix(span: SourceSpan) -> str | None:
    if span.cell is None:
        return None
    if span.cell_line is None:
        return f"cell {span.cell}"
    return f"cell {span.cell} line {span.cell_line}"
