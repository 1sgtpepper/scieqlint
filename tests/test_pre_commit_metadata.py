from __future__ import annotations

from pathlib import Path


def test_pre_commit_hook_metadata_targets_supported_sources() -> None:
    metadata = Path(".pre-commit-hooks.yaml").read_text(encoding="utf-8")

    assert "- id: scieqlint" in metadata
    assert "entry: scieqlint check" in metadata
    assert "language: python" in metadata
    assert "files: '\\.(md|markdown|tex|ipynb)$'" in metadata
    assert "require_serial: true" in metadata
