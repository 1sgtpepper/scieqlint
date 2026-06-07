"""Source document and line-index contracts."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath


class DocumentKind(Enum):
    MARKDOWN = "markdown"
    LATEX = "latex"
    NOTEBOOK = "notebook"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LineIndex:
    """Map Python string offsets to one-based line/column positions."""

    line_starts: tuple[int, ...]

    @classmethod
    def from_text(cls, text: str) -> LineIndex:
        starts = [0]
        for idx, char in enumerate(text):
            if char == "\n":
                starts.append(idx + 1)
        return cls(tuple(starts))

    def position(self, offset: int) -> tuple[int, int]:
        if offset < 0:
            raise ValueError("offset must be non-negative")
        line_idx = bisect_right(self.line_starts, offset) - 1
        line_start = self.line_starts[line_idx]
        return line_idx + 1, offset - line_start + 1


@dataclass(frozen=True, slots=True)
class SourceDocument:
    path: PurePosixPath
    text: str
    kind: DocumentKind
    line_index: LineIndex
    display_path: str

    @classmethod
    def from_text(cls, path: PurePosixPath, text: str, kind: DocumentKind) -> SourceDocument:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return cls(
            path=path,
            text=normalized,
            kind=kind,
            line_index=LineIndex.from_text(normalized),
            display_path=path.as_posix(),
        )
