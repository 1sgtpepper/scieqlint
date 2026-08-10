from __future__ import annotations

import json
import os
import runpy
import shutil
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


@pytest.fixture(scope="session")
def hook_repository(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    source_root = Path(__file__).resolve().parents[1]
    repository = tmp_path_factory.mktemp("scieqlint-hook-repository")
    shutil.copytree(source_root / "src", repository / "src")
    for filename in (".pre-commit-hooks.yaml", "pyproject.toml", "README.md", "SPEC.md", "LICENSE"):
        shutil.copy2(source_root / filename, repository / filename)
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "config", "user.name", "SciEqLint test")
    _git(
        repository,
        "add",
        "--",
        ".pre-commit-hooks.yaml",
        "pyproject.toml",
        "README.md",
        "SPEC.md",
        "LICENSE",
        "src",
    )
    _git(repository, "commit", "--quiet", "-m", "hook fixture")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repository, revision


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
    assert "entry: python -I -m scieqlint.pre_commit" in metadata
    assert 'args: ["--"]' in metadata
    assert "language: python" in metadata
    assert "stages: [pre-commit]" in metadata
    assert 'minimum_pre_commit_version: "3.2.0"' in metadata
    assert "files:" not in metadata
    assert "always_run: true" in metadata
    assert "pass_filenames: false" in metadata
    assert "require_serial:" not in metadata


def test_pre_commit_adapter_splits_options_from_option_shaped_path() -> None:
    assert pre_commit._split_arguments(("--strict-unknowns", "--", "--quiet.MARKDOWN")) == (
        ("--strict-unknowns",),
        ("--quiet.MARKDOWN",),
    )


def test_pre_commit_adapter_runs_one_project_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, returncode=7)

    monkeypatch.setattr(pre_commit.subprocess, "run", fake_run)

    assert pre_commit.main(("--",)) == 7
    assert calls == [
        (
            [pre_commit.sys.executable, "-I", "-m", "scieqlint", "check", "--"],
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

    monkeypatch.setattr(pre_commit.subprocess, "run", fake_run)

    assert (
        pre_commit.main(
            (
                "--strict-unknowns",
                "--config",
                "pyproject.toml",
                "--format",
                "json",
                "--output",
                "report.json",
                "--",
            )
        )
        == 7
    )
    assert calls == [
        [
            pre_commit.sys.executable,
            "-I",
            "-m",
            "scieqlint",
            "check",
            "--strict-unknowns",
            "--config",
            "pyproject.toml",
            "--format",
            "json",
            "--output",
            "report.json",
            "--",
        ]
    ]


@pytest.mark.parametrize("arguments", [(), ("--strict-unknowns", "chapter.MD")])
def test_pre_commit_adapter_rejects_missing_option_boundary(
    capsys: pytest.CaptureFixture[str],
    arguments: tuple[str, ...],
) -> None:
    assert pre_commit.main(arguments) == 2
    assert "must include '--'" in capsys.readouterr().err


def test_pre_commit_adapter_rejects_configured_filenames(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert pre_commit.main(("--", "chapter.MD")) == 2
    assert "does not accept filenames" in capsys.readouterr().err


def test_pre_commit_adapter_rejects_positional_paths_before_boundary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert pre_commit.main(("chapter.md", "--")) == 2
    assert "does not accept filenames" in capsys.readouterr().err


@pytest.mark.parametrize("variable", ["PRE_COMMIT_FROM_REF", "PRE_COMMIT_TO_REF"])
def test_pre_commit_adapter_rejects_revision_range(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    variable: str,
) -> None:
    monkeypatch.delenv("PRE_COMMIT_FROM_REF", raising=False)
    monkeypatch.delenv("PRE_COMMIT_TO_REF", raising=False)
    monkeypatch.setenv(variable, "ref")

    assert pre_commit.main(("--",)) == 2
    assert "revision-range runs are not supported" in capsys.readouterr().err


def test_pre_commit_adapter_module_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(pre_commit.subprocess, "run", fake_run)
    monkeypatch.setattr(pre_commit.sys, "argv", ["scieqlint.pre_commit", "--"])

    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(Path(pre_commit.__file__)), run_name="__main__")

    assert raised.value.code == 0
    assert calls == [[pre_commit.sys.executable, "-I", "-m", "scieqlint", "check", "--"]]


@pytest.mark.parametrize(("filename", "source"), _BOUNDARY_CASES)
def test_pre_commit_hook_checks_unchanged_project_context(
    tmp_path: Path,
    filename: str,
    source: str,
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
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


def test_pre_commit_hook_ignores_consumer_package_shadowing(
    tmp_path: Path,
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
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
    shadow_package = project / "scieqlint"
    shadow_package.mkdir()
    (shadow_package / "__init__.py").write_text(
        "raise RuntimeError('consumer package imported')\n",
        encoding="utf-8",
    )

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project)
    result = subprocess.run(
        ["pre-commit", "run", "scieqlint"],
        cwd=project,
        capture_output=True,
        text=True,
        env=environment,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert "REF001" in output
    assert "consumer package imported" not in output


def test_pre_commit_hook_scans_untracked_supported_files(
    tmp_path: Path,
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
    project = tmp_path / "project"
    _init_project(
        project,
        repository,
        revision,
        {"existing.md": "$$\nE = m c^2\n$$ {#duplicate}\n"},
    )
    (project / "draft.md").write_text("$$\nF = m a\n$$ {#duplicate}\n", encoding="utf-8")

    result = subprocess.run(
        ["pre-commit", "run", "scieqlint"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "REF001" in output


@pytest.mark.parametrize(
    ("selection", "stage_unrelated"),
    [
        (("--all-files",), False),
        (("--files", "chapter.md"), False),
        (("--all-files",), True),
    ],
)
def test_pre_commit_hook_checks_every_selection_mode(
    tmp_path: Path,
    selection: tuple[str, ...],
    stage_unrelated: bool,
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
    project = tmp_path / "project"
    _init_project(
        project,
        repository,
        revision,
        {
            "existing.md": "$$\nE = m c^2\n$$ {#duplicate}\n",
            "chapter.md": "$$\nF = m a\n$$ {#duplicate}\n",
        },
    )
    if stage_unrelated:
        (project / "notes.txt").write_text("plain text\n", encoding="utf-8")
        _git(project, "add", "--", "notes.txt")

    result = subprocess.run(
        ["pre-commit", "run", "scieqlint", *selection],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "REF001" in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("selection", "staged_source", "working_source", "expected_returncode"),
    [
        (
            (),
            "$$\nF = m a\n$$ {#duplicate}\n",
            "plain text\n",
            1,
        ),
        (
            (),
            "plain text\nadditional staged text\n",
            "$$\nF = m a\n$$ {#duplicate}\n",
            0,
        ),
        (
            ("--all-files",),
            "$$\nF = m a\n$$ {#duplicate}\n",
            "plain text\n",
            0,
        ),
        (
            ("--all-files",),
            "plain text\nadditional staged text\n",
            "$$\nF = m a\n$$ {#duplicate}\n",
            1,
        ),
        (
            ("--files", "chapter.md"),
            "$$\nF = m a\n$$ {#duplicate}\n",
            "plain text\n",
            0,
        ),
        (
            ("--files", "chapter.md"),
            "plain text\nadditional staged text\n",
            "$$\nF = m a\n$$ {#duplicate}\n",
            1,
        ),
    ],
)
def test_pre_commit_hook_matches_pre_commit_staging_mode(
    tmp_path: Path,
    selection: tuple[str, ...],
    staged_source: str,
    working_source: str,
    expected_returncode: int,
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
    project = tmp_path / "project"
    _init_project(
        project,
        repository,
        revision,
        {
            "existing.md": "$$\nE = m c^2\n$$ {#duplicate}\n",
            "chapter.md": "plain text\n",
        },
    )
    (project / "chapter.md").write_text(staged_source, encoding="utf-8")
    _git(project, "add", "--", "chapter.md")
    (project / "chapter.md").write_text(working_source, encoding="utf-8")

    result = subprocess.run(
        ["pre-commit", "run", "scieqlint", *selection],
        cwd=project,
        capture_output=True,
        text=True,
    )

    output = result.stdout + result.stderr
    assert result.returncode == expected_returncode
    assert ("REF001" in output) is (expected_returncode == 1)
    assert (project / "chapter.md").read_text(encoding="utf-8") == working_source


@pytest.mark.parametrize("operation", ["delete", "rename"])
def test_pre_commit_hook_checks_when_supported_source_leaves_project(
    tmp_path: Path,
    operation: str,
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
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


def test_pre_commit_hook_checks_mixed_staged_deletion(
    tmp_path: Path,
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
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
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
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
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
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


def test_pre_commit_hook_forwards_consumer_arguments(
    tmp_path: Path,
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
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


def test_pre_commit_hook_rejects_positional_consumer_path(
    tmp_path: Path,
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
    project = tmp_path / "project"
    _init_project(
        project,
        repository,
        revision,
        {
            "existing.md": "$$\nE = m c^2\n$$ {#duplicate}\n",
            "chapter.md": "$$\nF = m a\n$$ {#duplicate}\n",
        },
        hook_args=("chapter.md", "--"),
    )

    result = subprocess.run(
        ["pre-commit", "run", "scieqlint"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "does not accept filenames" in output
    assert "REF001" not in output


def test_pre_commit_hook_rejects_consumer_arguments_without_boundary(
    tmp_path: Path,
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
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


def test_pre_commit_hook_ignores_explicit_file_selection_for_project_scan(
    tmp_path: Path,
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
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


def test_pre_commit_hook_ignores_consumer_exclude_for_project_scan(
    tmp_path: Path,
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
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


def test_pre_commit_hook_checks_unrelated_staged_changes(
    tmp_path: Path,
    hook_repository: tuple[Path, str],
) -> None:
    repository, revision = hook_repository
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

    assert result.returncode == 1
    assert "REF001" in result.stdout + result.stderr
