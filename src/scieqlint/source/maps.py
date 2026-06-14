"""Source identity, source maps, and origin metadata for architecture-owned facts.

This module is intentionally small. It does not discover files and it does not
parse source text. It gives all later layers stable document IDs and spans so
that reporters never need to rescan source files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from scieqlint.diag.model import SourceSpan
from scieqlint.io.source import SourceDocument


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """Stable identity for a loaded source document."""

    document_id: str
    path: PurePosixPath
    kind: str
    generated: bool = False


@dataclass(frozen=True, slots=True)
class Origin:
    """Optional source provenance for generated or converted facts."""

    source_document_id: str | None = None
    source_span: SourceSpan | None = None
    tool: str | None = None
    tool_version: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class SourceMap:
    """A deterministic offset-to-span helper for one document."""

    identity: SourceIdentity
    document: SourceDocument

    @classmethod
    def for_document(cls, document: SourceDocument) -> SourceMap:
        return cls(
            SourceIdentity(
                document_id=document.path.as_posix(),
                path=document.path,
                kind=document.kind.value,
            ),
            document,
        )

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
