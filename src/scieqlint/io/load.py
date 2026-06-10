"""Source loading helpers for path-based APIs."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from scieqlint.diag.model import SourceSpan
from scieqlint.io.source import DocumentKind, SourceDocument


def load_source_document(path: Path, *, absolute_paths: bool) -> SourceDocument:
    """Read a supported source file into the analyzer document model."""
    return SourceDocument.from_text(
        display_path(path, absolute_paths=absolute_paths),
        path.read_text(encoding="utf-8"),
        document_kind(path),
    )


def display_path(path: Path, *, absolute_paths: bool) -> PurePosixPath:
    if absolute_paths:
        return PurePosixPath(path.resolve().as_posix())
    try:
        return PurePosixPath(path.resolve().relative_to(Path.cwd().resolve()).as_posix())
    except ValueError:
        return PurePosixPath(path.as_posix())


def document_kind(path: Path) -> DocumentKind:
    match path.suffix.lower():
        case ".tex":
            return DocumentKind.LATEX
        case ".ipynb":
            return DocumentKind.NOTEBOOK
        case _:
            return DocumentKind.MARKDOWN


def file_start_span(path: Path, *, absolute_paths: bool) -> SourceSpan:
    return SourceSpan(
        path=display_path(path, absolute_paths=absolute_paths),
        start=0,
        end=0,
        line=1,
        col=1,
        end_line=1,
        end_col=1,
    )
