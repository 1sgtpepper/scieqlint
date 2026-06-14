"""Architecture-preview library API.

This module is intentionally separate from the existing `scieqlint.api` so the
implementation can be reviewed without changing the stable v0.1 CLI/API path.
A later integration PR can rename or re-export these functions once schemas are
accepted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path, PurePosixPath

from scieqlint.check.suppressions import apply_suppressions
from scieqlint.compat.architecture_pipeline import analyze_documents_architecture
from scieqlint.config.model import Config
from scieqlint.diag.baseline import (
    BaselineIdentity,
    apply_baseline,
    baseline_identities_from_json,
)
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import MathBlock, MathContainer
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


def apply_config_policy_architecture(
    result: AnalysisResult,
    config: Config,
) -> AnalysisResult:
    """Apply CLI/project policy after architecture DiagnosticIR conversion."""
    diagnostics = apply_suppressions(
        result.diagnostics,
        documents=result.snapshot.documents,
        blocks=_architecture_math_blocks(result),
    )
    diagnostics = apply_baseline(
        diagnostics,
        _load_architecture_baselines(config),
    )
    return replace(result, diagnostics=diagnostics)


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


def _architecture_math_blocks(result: AnalysisResult) -> tuple[MathBlock, ...]:
    blocks: list[MathBlock] = []
    for fact in result.snapshot.display_math:
        span = fact.span
        if span is None:
            continue
        container = (
            MathContainer.MARKDOWN_FENCE
            if fact.container == "fenced-math"
            else MathContainer.MARKDOWN_DISPLAY
        )
        blocks.append(
            MathBlock(
                text=fact.body,
                span=span,
                block_id=fact.fact_id,
                container=container,
            )
        )
    return tuple(blocks)


def _load_architecture_baselines(config: Config) -> frozenset[BaselineIdentity]:
    identities: set[BaselineIdentity] = set()
    for raw in config.baseline.files:
        path = Path(raw)
        if not path.is_absolute():
            path = _architecture_project_root(config) / path
        identities.update(baseline_identities_from_json(path.read_text(encoding="utf-8")))
    return frozenset(identities)


def _architecture_project_root(config: Config) -> Path:
    root = Path(config.project.root.as_posix())
    if root.is_absolute():
        return root
    if config.path is None:
        return Path.cwd() / root
    return Path(config.path.as_posix()).parent / root
