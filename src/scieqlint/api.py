"""Public API for SciEqLint."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from scieqlint.app import _AnalysisRun as _AnalysisRun  # pyright: ignore[reportPrivateUsage]
from scieqlint.app import (
    _run_check_paths as _app_run_check_paths,  # pyright: ignore[reportPrivateUsage]
)
from scieqlint.app import (
    _run_graph_paths as _app_run_graph_paths,  # pyright: ignore[reportPrivateUsage]
)
from scieqlint.app import check_documents as _check_documents
from scieqlint.app import graph_documents as _graph_documents
from scieqlint.config.load import load_config
from scieqlint.config.model import Config
from scieqlint.diag.model import CheckResult
from scieqlint.graph.model import Graph
from scieqlint.io.source import SourceDocument

__all__ = ["check_documents", "check_paths", "graph_documents", "graph_paths", "load_config"]


def check_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
    no_algebra: bool = False,
    inline_math: bool = False,
    strict_unknowns: bool = False,
    absolute_paths: bool = False,
) -> CheckResult:
    """Check paths and return a deterministic result."""
    return _run_check_paths(
        paths,
        config_path=config_path,
        no_algebra=no_algebra,
        inline_math=inline_math,
        strict_unknowns=strict_unknowns,
        absolute_paths=absolute_paths,
    ).result


def check_documents(
    documents: Sequence[SourceDocument],
    *,
    config: Config,
    accessibility_metadata: Mapping[str, str] | None = None,
) -> CheckResult:
    """Check already-loaded documents with caller-owned accessibility metadata."""
    return _check_documents(
        documents,
        config=config,
        accessibility_metadata=accessibility_metadata,
    )


def graph_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
) -> Graph:
    """Build graph data from paths."""
    return _run_graph_paths(paths, config_path=config_path).result


def graph_documents(
    documents: Sequence[SourceDocument],
    *,
    config: Config,
) -> Graph:
    """Build graph data from already-loaded documents."""
    return _graph_documents(documents, config=config)


def _run_check_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
    no_algebra: bool = False,
    inline_math: bool = False,
    strict_unknowns: bool = False,
    absolute_paths: bool = False,
) -> _AnalysisRun[CheckResult]:
    return _app_run_check_paths(
        paths,
        config_path=config_path,
        no_algebra=no_algebra,
        inline_math=inline_math,
        strict_unknowns=strict_unknowns,
        absolute_paths=absolute_paths,
    )


def _run_graph_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
) -> _AnalysisRun[Graph]:
    return _app_run_graph_paths(paths, config_path=config_path)
