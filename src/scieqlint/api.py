"""Public API for SciEqLint."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from scieqlint.app import check_documents as _check_documents
from scieqlint.app import check_paths as _check_paths
from scieqlint.app import graph_documents as _graph_documents
from scieqlint.app import graph_paths as _graph_paths
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
    return _check_paths(
        paths,
        config_path=config_path,
        no_algebra=no_algebra,
        inline_math=inline_math,
        strict_unknowns=strict_unknowns,
        absolute_paths=absolute_paths,
    )


def check_documents(
    documents: Sequence[SourceDocument],
    *,
    config: Config,
) -> CheckResult:
    """Check already-loaded documents."""
    return _check_documents(documents, config=config)


def graph_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
) -> Graph:
    """Build graph data from paths."""
    return _graph_paths(paths, config_path=config_path)


def graph_documents(
    documents: Sequence[SourceDocument],
    *,
    config: Config,
) -> Graph:
    """Build graph data from already-loaded documents."""
    return _graph_documents(documents, config=config)
