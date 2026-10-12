"""Offset-to-span mapping for loaded source documents.

This module is intentionally small. It does not discover files and it does not
parse source text. It maps offsets from an already-loaded document into spans,
so reporters never need to rescan source files.
"""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.diag.model import SourceSpan
from scieqlint.io.source import SourceDocument


@dataclass(frozen=True, slots=True)
class SourceMap:
    """A deterministic offset-to-span helper for one document."""

    document: SourceDocument

    def span(self, start: int, end: int) -> SourceSpan:
        """Build a SourceSpan from Python string offsets.

        End line/column intentionally point at the last covered character to
        match the existing v0.1 SourceSpan convention used by reporters.
        """

        if start < 0 or end < start:
            raise ValueError("invalid span offsets")
        line, col = self.document.line_index.position(start)
        end_line, end_col = self.document.line_index.position(max(start, end - 1))
        return SourceSpan(
            path=self.document.path,
            start=start,
            end=end,
            line=line,
            col=col,
            end_line=end_line,
            end_col=end_col,
        )
