from __future__ import annotations

import re
from pathlib import Path


def test_pre_commit_hook_metadata_targets_supported_sources() -> None:
    metadata = Path(".pre-commit-hooks.yaml").read_text(encoding="utf-8")

    assert "- id: scieqlint" in metadata
    assert "entry: scieqlint check" in metadata
    assert 'args: ["--"]' in metadata
    assert "language: python" in metadata
    match = re.search(r"^  files: '([^']+)'$", metadata, re.MULTILINE)
    assert match is not None
    file_pattern = re.compile(match.group(1))
    assert file_pattern.search("notes.MD") is not None
    assert file_pattern.search("equations.tex") is not None
    assert file_pattern.search("data.csv") is None
    assert "pass_filenames: false" in metadata
    assert "require_serial: true" in metadata
