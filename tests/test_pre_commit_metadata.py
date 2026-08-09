from __future__ import annotations

import json
import re
import runpy
import subprocess
from pathlib import Path

import pytest

from scieqlint import pre_commit

_BOUNDARY_CASES = (
    (
        "chapter.MD",
        "$$\nF = m a\n$$ {#duplicate}\n",
    ),
    (
        "--quiet.MARKDOWN",
        "$$\nF = m a\n$$ {#duplicate}\n",
    ),
    (
        "spaced μ-source.TeX",
        "\\begin{equation}\n\\label{duplicate}\nF = m a\n\\end{equation}\n",
    ),
    (
        "notebook.IPYNB",
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": "$$\nF = m a\n$$ {#duplicate}\n",
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
    ),
)


def _git(project: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_project(
    project: Path,
    repository: Path,
    revision: str,
    files: dict[str, str],
) -> None:
    project.mkdir()
    _git(project, "init", "--quiet")
    _git(project, "config", "user.email", "test@example.invalid")
    _git(project, "config", "user.name", "SciEqLint test")
    for name, source in files.items():
        (project / name).write_text(source, encoding="utf-8")
    (project / ".pre-commit-config.yaml").write_text(
        "repos:\n"
        f"  - repo: {json.dumps(str(repository))}\n"
        f"    rev: {revision}\n"
        "    hooks:\n"
        "      - id: scieqlint\n",
        encoding="utf-8",
    )
    _git(project, "add", "--", ".pre-commit-config.yaml", *files)
    _git(project, "commit", "--quiet", "-m", "fixture")


def test_pre_commit_hook_metadata_targets_supported_sources() -> None:
    metadata = Path(".pre-commit-hooks.yaml").read_text(encoding="utf-8")

    assert "- id: scieqlint" in metadata
    assert "entry: python -m scieqlint.pre_commit" in metadata
    assert 'args: ["--"]' in metadata
    assert "language: python" in metadata
    match = re.search(r"^  files: '([^']+)'$", metadata, re.MULTILINE)
    assert match is not None
    file_pattern = re.compile(match.group(1))
    for path in (
        "notes.md",
        "notes.MD",
        "equations.markdown",
        "equations.MARKDOWN",
        "equations.tex",
        "equations.TeX",
        "notes.ipynb",
        "notes.IPYNB",
    ):
        assert file_pattern.search(path) is not None
    for path in ("data.csv", "paper.md.tmp", "paper.tex.backup"):
        assert file_pattern.search(path) is None
    assert "always_run: true" in metadata
    assert "pass_filenames: true" in metadata
    assert "require_serial: true" in metadata


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("paper.md", True),
        ("paper.MD", True),
        ("paper.tex", True),
        ("paper.IPYNB", True),
        ("paper.md.tmp", False),
        ("paper", False),
    ],
)
def test_pre_commit_adapter_classifies_source_suffix(
    path: str,
    expected: bool,
) -> None:
    assert pre_commit._is_supported(path) is expected


def test_pre_commit_adapter_reads_deleted_and_renamed_index_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=(
            b"R100\0definitions.md\0definitions.md.tmp\0C100\0source.tex\0copy.tex\0D\0notes.txt\0"
        ),
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        assert command == [
            "git",
            "diff",
            "--cached",
            "--name-status",
            "--diff-filter=ACDMRTUXB",
            "-z",
            "--",
        ]
        assert kwargs == {"check": True, "capture_output": True}
        return completed

    monkeypatch.setattr(pre_commit.subprocess, "run", fake_run)

    assert pre_commit._staged_paths() == (
        "definitions.md",
        "definitions.md.tmp",
        "source.tex",
        "copy.tex",
        "notes.txt",
    )


def test_pre_commit_adapter_filters_option_separator() -> None:
    assert pre_commit._candidate_paths(("--", "--quiet.MARKDOWN")) == ("--quiet.MARKDOWN",)


def test_pre_commit_adapter_runs_project_check_for_supported_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, returncode=7)

    def unexpected_staged_paths() -> tuple[str, ...]:
        raise AssertionError("candidate should be used")

    monkeypatch.setattr(pre_commit.subprocess, "run", fake_run)
    monkeypatch.setattr(pre_commit, "_staged_paths", unexpected_staged_paths)

    assert pre_commit.main(("--", "chapter.MD")) == 7
    assert calls == [
        (
            [pre_commit.sys.executable, "-m", "scieqlint", "check", "--"],
            {"check": False},
        )
    ]


@pytest.mark.parametrize(
    ("staged_paths", "expected_returncode"),
    [((), 0), (("unrelated.txt",), 0), (("deleted.md",), 5)],
)
def test_pre_commit_adapter_falls_back_to_staged_paths(
    monkeypatch: pytest.MonkeyPatch,
    staged_paths: tuple[str, ...],
    expected_returncode: int,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode=5)

    monkeypatch.setattr(pre_commit, "_staged_paths", lambda: staged_paths)
    monkeypatch.setattr(pre_commit.subprocess, "run", fake_run)

    assert pre_commit.main(()) == expected_returncode
    assert bool(calls) is bool(expected_returncode)


def test_pre_commit_adapter_module_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args, returncode=0, stdout=b"")

    monkeypatch.setattr(pre_commit.subprocess, "run", fake_run)
    monkeypatch.setattr(pre_commit.sys, "argv", ["scieqlint.pre_commit", "notes.txt"])

    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(Path(pre_commit.__file__)), run_name="__main__")

    assert raised.value.code == 0


@pytest.mark.parametrize(("filename", "source"), _BOUNDARY_CASES)
def test_pre_commit_hook_checks_unchanged_project_context(
    tmp_path: Path,
    filename: str,
    source: str,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    project = tmp_path / "project"
    _init_project(
        project,
        repository,
        revision,
        {"existing.md": "$$\nE = m c^2\n$$ {#duplicate}\n"},
    )
    (project / filename).write_text(source, encoding="utf-8")
    _git(project, "add", "--", filename)

    result = subprocess.run(
        ["pre-commit", "run", "scieqlint"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "REF001" in output
    assert "No such option" not in output


@pytest.mark.parametrize("operation", ["delete", "rename"])
def test_pre_commit_hook_checks_when_supported_source_leaves_project(
    tmp_path: Path,
    operation: str,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    project = tmp_path / "project"
    _init_project(
        project,
        repository,
        revision,
        {
            "definitions.md": "$$\nE = m c^2\n$$ {#energy}\n",
            "references.md": "See {eq}`energy`.\n",
        },
    )
    if operation == "delete":
        _git(project, "rm", "--", "definitions.md")
    else:
        _git(project, "mv", "--", "definitions.md", "definitions.md.tmp")

    result = subprocess.run(
        ["pre-commit", "run", "scieqlint", "-v"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = result.stdout + result.stderr
    assert "REF002" in output
    assert "references.md" in output


def test_pre_commit_hook_skips_unrelated_changes(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    project = tmp_path / "project"
    _init_project(
        project,
        repository,
        revision,
        {
            "first.md": "$$\nE = m c^2\n$$ {#duplicate}\n",
            "second.md": "$$\nF = m a\n$$ {#duplicate}\n",
        },
    )
    (project / "notes.txt").write_text("plain text\n", encoding="utf-8")
    _git(project, "add", "--", "notes.txt")

    result = subprocess.run(
        ["pre-commit", "run", "scieqlint"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "REF001" not in result.stdout + result.stderr
