from __future__ import annotations

import json
import runpy
import subprocess
from collections.abc import Sequence
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
    hook_args: Sequence[str] | None = None,
    hook_exclude: str | None = None,
) -> None:
    project.mkdir()
    _git(project, "init", "--quiet")
    _git(project, "config", "user.email", "test@example.invalid")
    _git(project, "config", "user.name", "SciEqLint test")
    for name, source in files.items():
        (project / name).write_text(source, encoding="utf-8")
    configured_hook = ""
    if hook_args is not None:
        configured_hook += f"        args: {json.dumps(list(hook_args))}\n"
    if hook_exclude is not None:
        configured_hook += f"        exclude: {json.dumps(hook_exclude)}\n"
    (project / ".pre-commit-config.yaml").write_text(
        "repos:\n"
        f"  - repo: {json.dumps(str(repository))}\n"
        f"    rev: {revision}\n"
        "    hooks:\n"
        "      - id: scieqlint\n"
        f"{configured_hook}",
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
    assert "stages: [pre-commit]" in metadata
    assert "files:" not in metadata
    assert "always_run: true" in metadata
    assert "pass_filenames: false" in metadata
    assert "require_serial:" not in metadata


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


def test_pre_commit_adapter_parses_all_staged_path_roles(
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

    records = pre_commit._staged_records()
    assert records == (
        ("R", ("definitions.md", "definitions.md.tmp")),
        ("C", ("source.tex", "copy.tex")),
        ("D", ("notes.txt",)),
    )


def test_pre_commit_adapter_splits_options_from_option_shaped_path() -> None:
    assert pre_commit._split_arguments(("--strict-unknowns", "--", "--quiet.MARKDOWN")) == (
        ("--strict-unknowns",),
        ("--quiet.MARKDOWN",),
    )


def test_pre_commit_adapter_runs_project_check_for_supported_staged_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, returncode=7)

    monkeypatch.setattr(
        pre_commit,
        "_staged_records",
        lambda: (("M", ("chapter.MD",)),),
    )
    monkeypatch.setattr(pre_commit.subprocess, "run", fake_run)

    assert pre_commit.main(("--",)) == 7
    assert calls == [
        (
            [pre_commit.sys.executable, "-m", "scieqlint", "check", "--"],
            {"check": False},
        )
    ]


def test_pre_commit_adapter_forwards_checker_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode=7)

    monkeypatch.setattr(
        pre_commit,
        "_staged_records",
        lambda: (("M", ("chapter.MD",)),),
    )
    monkeypatch.setattr(pre_commit.subprocess, "run", fake_run)

    assert pre_commit.main(("--strict-unknowns", "--")) == 7
    assert calls == [
        [
            pre_commit.sys.executable,
            "-m",
            "scieqlint",
            "check",
            "--strict-unknowns",
            "--",
        ]
    ]


def test_pre_commit_adapter_rejects_missing_option_boundary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert pre_commit.main(("--strict-unknowns", "chapter.MD")) == 2
    assert "must include '--'" in capsys.readouterr().err


def test_pre_commit_adapter_rejects_configured_filenames(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert pre_commit.main(("--", "chapter.MD")) == 2
    assert "does not accept filenames" in capsys.readouterr().err


def test_pre_commit_adapter_rejects_revision_range(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("PRE_COMMIT_FROM_REF", "A")
    monkeypatch.setenv("PRE_COMMIT_TO_REF", "B")

    assert pre_commit.main(("--",)) == 2
    assert "revision-range runs are not supported" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("staged_records", "invokes_checker"),
    [
        ((), False),
        ((("M", ("unrelated.txt",)),), False),
        ((("D", ("deleted.md",)),), True),
        ((("R", ("definitions.md", "definitions.tmp")),), True),
        ((("R", ("definitions.tmp", "definitions.md")),), True),
        ((("T", ("paper.tex",)),), True),
    ],
)
def test_pre_commit_adapter_triggers_from_any_staged_path_role(
    monkeypatch: pytest.MonkeyPatch,
    staged_records: tuple[tuple[str, tuple[str, ...]], ...],
    invokes_checker: bool,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode=5)

    monkeypatch.setattr(pre_commit, "_staged_records", lambda: staged_records)
    monkeypatch.setattr(pre_commit.subprocess, "run", fake_run)

    assert pre_commit.main(("--",)) == (5 if invokes_checker else 0)
    assert calls == (
        [[pre_commit.sys.executable, "-m", "scieqlint", "check", "--"]] if invokes_checker else []
    )


def test_pre_commit_adapter_runs_one_project_check_for_all_staged_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode=5)

    monkeypatch.setattr(
        pre_commit,
        "_staged_records",
        lambda: (
            ("M", ("notes.txt",)),
            ("R", ("definitions.md", "definitions.tmp")),
            ("D", ("deleted.md",)),
            ("M", ("chapter.MD",)),
        ),
    )
    monkeypatch.setattr(pre_commit.subprocess, "run", fake_run)

    assert pre_commit.main(("--",)) == 5
    assert calls == [[pre_commit.sys.executable, "-m", "scieqlint", "check", "--"]]


def test_pre_commit_adapter_module_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command)
        if command[0] == "git":
            return subprocess.CompletedProcess(command, returncode=0, stdout=b"M\0chapter.MD\0")
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(pre_commit.subprocess, "run", fake_run)
    monkeypatch.setattr(pre_commit.sys, "argv", ["scieqlint.pre_commit", "--"])

    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(Path(pre_commit.__file__)), run_name="__main__")

    assert raised.value.code == 0
    assert calls == [
        [
            "git",
            "diff",
            "--cached",
            "--name-status",
            "--diff-filter=ACDMRTUXB",
            "-z",
            "--",
        ],
        [pre_commit.sys.executable, "-m", "scieqlint", "check", "--"],
    ]


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


def test_pre_commit_hook_checks_mixed_staged_deletion(tmp_path: Path) -> None:
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
            "notes.txt": "plain text\n",
        },
    )
    (project / "notes.txt").write_text("unrelated staged text\n", encoding="utf-8")
    _git(project, "add", "--", "notes.txt")
    _git(project, "rm", "--", "definitions.md")

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


def test_pre_commit_hook_checks_rename_source_when_destination_is_filtered(
    tmp_path: Path,
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
            "notes.txt": "plain text\n",
        },
        hook_exclude=r"^definitions\.tmp$",
    )
    _git(project, "mv", "--", "definitions.md", "definitions.tmp")
    (project / "notes.txt").write_text("unrelated staged text\n", encoding="utf-8")
    _git(project, "add", "--", "notes.txt")

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


def test_pre_commit_hook_runs_one_project_check_for_large_staged_set(
    tmp_path: Path,
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
    staged_paths = [f"candidate-{index:04d}-{'x' * 180}.md" for index in range(700)]
    for path in staged_paths:
        (project / path).write_text("plain text\n", encoding="utf-8")
    (project / "trigger.md").write_text("$$\nF = m a\n$$ {#duplicate}\n", encoding="utf-8")
    _git(project, "add", "--", *staged_paths, "trigger.md")

    result = subprocess.run(
        ["pre-commit", "run", "scieqlint", "-v"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert output.count("REF001") == 1


def test_pre_commit_hook_forwards_consumer_arguments(tmp_path: Path) -> None:
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
        {"trig.md": "plain text\n"},
        hook_args=("--strict-unknowns", "--"),
    )
    (project / "trig.md").write_text("$$\n\\sin(x) = x\n$$\n", encoding="utf-8")
    _git(project, "add", "--", "trig.md")

    result = subprocess.run(
        ["pre-commit", "run", "scieqlint", "-v"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "error PARSE021" in output
    assert "No such option" not in output


def test_pre_commit_hook_rejects_consumer_arguments_without_boundary(tmp_path: Path) -> None:
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
        {"trig.md": "plain text\n"},
        hook_args=("--strict-unknowns",),
    )
    (project / "trig.md").write_text("$$\n\\sin(x) = x\n$$\n", encoding="utf-8")
    _git(project, "add", "--", "trig.md")

    result = subprocess.run(
        ["pre-commit", "run", "scieqlint", "-v"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "must include '--'" in output


def test_pre_commit_hook_uses_staged_index_for_explicit_file_selection(
    tmp_path: Path,
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
            "existing.md": "$$\nE = m c^2\n$$ {#duplicate}\n",
            "notes.txt": "plain text\n",
        },
    )
    (project / "chapter.md").write_text("$$\nF = m a\n$$ {#duplicate}\n", encoding="utf-8")
    _git(project, "add", "--", "chapter.md")

    result = subprocess.run(
        ["pre-commit", "run", "scieqlint", "--files", "notes.txt"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "REF001" in output


def test_pre_commit_hook_uses_staged_index_despite_consumer_exclude(tmp_path: Path) -> None:
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
            "existing.md": "$$\nE = m c^2\n$$ {#duplicate}\n",
            "chapter.md": "plain text\n",
        },
        hook_exclude=r"^chapter\.md$",
    )
    (project / "chapter.md").write_text("$$\nF = m a\n$$ {#duplicate}\n", encoding="utf-8")
    _git(project, "add", "--", "chapter.md")

    result = subprocess.run(
        ["pre-commit", "run", "scieqlint"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "REF001" in result.stdout + result.stderr


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
