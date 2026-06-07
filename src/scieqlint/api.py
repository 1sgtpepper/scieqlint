"""Public API for SciEqLint."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from scieqlint.app import check_documents as _check_documents
from scieqlint.app import check_paths as _check_paths
from scieqlint.config.load import load_config
from scieqlint.config.model import Config
from scieqlint.diag.model import CheckResult
from scieqlint.io.source import SourceDocument

__all__ = ["check_documents", "check_paths", "load_config"]


def check_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
) -> CheckResult:
    """Check paths and return a deterministic result."""
    return _check_paths(paths, config_path=config_path)


def check_documents(
    documents: Sequence[SourceDocument],
    *,
    config: Config,
) -> CheckResult:
    """Check already-loaded documents."""
    return _check_documents(documents, config=config)
