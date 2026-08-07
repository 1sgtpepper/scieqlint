from __future__ import annotations

import json
import re
import subprocess
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


def test_pre_commit_hook_checks_unstaged_project_context(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    project = tmp_path / "project"
    project.mkdir()

    def git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=project,
            check=True,
            capture_output=True,
            text=True,
        )

    git("init", "--quiet")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "SciEqLint test")
    (project / "existing.md").write_text(
        "$$\nE = m c^2\n$$ {#duplicate}\n",
        encoding="utf-8",
    )
    (project / ".pre-commit-config.yaml").write_text(
        "repos:\n"
        f"  - repo: {json.dumps(str(repository))}\n"
        f"    rev: {revision}\n"
        "    hooks:\n"
        "      - id: scieqlint\n",
        encoding="utf-8",
    )
    git("add", "existing.md", ".pre-commit-config.yaml")
    git("commit", "--quiet", "-m", "fixture")

    (project / "chapter.MD").write_text(
        "$$\nF = m a\n$$ {#duplicate}\n",
        encoding="utf-8",
    )
    git("add", "chapter.MD")

    result = subprocess.run(
        ["pre-commit", "run", "scieqlint"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "REF001" in result.stdout + result.stderr
