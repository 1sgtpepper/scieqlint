"""Architecture-preview library API.

This module is intentionally separate from the existing `scieqlint.api` so the
implementation can be reviewed without changing the stable v0.1 CLI/API path.
A later integration PR can rename or re-export these functions once schemas are
accepted.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from scieqlint.compat.architecture_pipeline import analyze_documents_architecture
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.schema.result import AnalysisResult

_SUPPORTED_SUFFIXES = {".md", ".markdown", ".myst", ".qmd"}


def analyze_paths_architecture(
    paths: Sequence[str | Path],
    *,
    profiles: tuple[str, ...] = ("scientific-myst",),
    generated_pairs: tuple[tuple[str, str], ...] = (),
) -> AnalysisResult:
    """Load supported source files and run the architecture pipeline.

    This helper deliberately does not replace `check_paths()`. It is an
    opt-in bridge used by tests, examples, and the future CLI wire-up PR.
    """

    documents = tuple(_load_documents(paths))
    return analyze_documents_architecture(
        documents,
        profiles=profiles,
        generated_pairs=generated_pairs,
    )


def _load_documents(paths: Sequence[str | Path]) -> tuple[SourceDocument, ...]:
    files: list[Path] = []
    for raw in paths or [Path(".")]:
        path = Path(raw)
        if path.is_dir():
            files.extend(
                sorted(
                    child
                    for child in path.rglob("*")
                    if child.suffix.lower() in _SUPPORTED_SUFFIXES
                )
            )
        elif path.suffix.lower() in _SUPPORTED_SUFFIXES:
            files.append(path)
    documents: list[SourceDocument] = []
    for path in sorted(dict.fromkeys(files)):
        documents.append(
            SourceDocument.from_text(
                PurePosixPath(path.as_posix()),
                path.read_text(encoding="utf-8"),
                DocumentKind.MARKDOWN,
            )
        )
    return tuple(documents)
