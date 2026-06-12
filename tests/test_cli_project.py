from __future__ import annotations

import json

from click.testing import CliRunner

from scieqlint.cli import main


def test_check_discovers_latex_source_files(tmp_path) -> None:
    doc = tmp_path / "paper.tex"
    doc.write_text(
        "\\begin{equation}\n(a+b)^2 = a^2 + b^2\n\\end{equation}\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(tmp_path)])

    assert result.exit_code == 1
    assert "ALG001" in result.output
    assert "paper.tex" in result.output


def test_check_discovers_notebook_source_files(tmp_path) -> None:
    doc = tmp_path / "notes.ipynb"
    doc.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": "$$\n(a+b)^2 = a^2 + b^2\n$$\n",
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(tmp_path)])

    assert result.exit_code == 1
    assert "ALG001" in result.output
    assert "notes.ipynb" in result.output


def test_config_ignore_files_excludes_discovered_paths(tmp_path) -> None:
    kept = tmp_path / "kept.md"
    ignored = tmp_path / "ignored.md"
    config = tmp_path / "scieqlint.toml"
    kept.write_text("# Kept\n", encoding="utf-8")
    ignored.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    config.write_text(
        f'[ignore]\nfiles = ["{ignored.resolve().as_posix()}"]\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(tmp_path), "--config", str(config)])

    assert result.exit_code == 0
    assert "files checked: 1" in result.output


def test_config_ignore_files_does_not_exclude_explicit_file(tmp_path) -> None:
    doc = tmp_path / "ignored.md"
    config = tmp_path / "scieqlint.toml"
    doc.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    config.write_text(
        f'[ignore]\nfiles = ["{doc.resolve().as_posix()}"]\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc), "--config", str(config)])

    assert result.exit_code == 1
    assert "ALG001" in result.output


def test_discovered_symlink_to_file_outside_project_root_is_skipped(tmp_path) -> None:
    root = tmp_path / "book"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    target = external / "outside.md"
    link = root / "linked.md"
    config = tmp_path / "scieqlint.toml"
    target.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    link.symlink_to(target)
    config.write_text('[project]\nroot = "book"\n', encoding="utf-8")

    result = CliRunner().invoke(main, ["check", str(root), "--config", str(config)])

    assert result.exit_code == 0
    assert "files checked: 0" in result.output
    assert "ALG001" not in result.output


def test_glob_discovery_skips_files_reached_through_external_symlink_dir(tmp_path) -> None:
    root = tmp_path / "book"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    target = external / "outside.md"
    link_dir = root / "linked"
    config = tmp_path / "scieqlint.toml"
    target.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    link_dir.symlink_to(external, target_is_directory=True)
    config.write_text('[project]\nroot = "book"\n', encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["check", str(root / "**" / "*.md"), "--config", str(config)],
    )

    assert result.exit_code == 0
    assert "files checked: 0" in result.output
    assert "ALG001" not in result.output


def test_glob_rooted_at_external_symlink_dir_inside_project_is_skipped(tmp_path) -> None:
    root = tmp_path / "book"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    target = external / "outside.md"
    link_dir = root / "linked"
    config = tmp_path / "scieqlint.toml"
    target.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    link_dir.symlink_to(external, target_is_directory=True)
    config.write_text('[project]\nroot = "book"\n', encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["check", str(link_dir / "**" / "*.md"), "--config", str(config)],
    )

    assert result.exit_code == 0
    assert "files checked: 0" in result.output
    assert "ALG001" not in result.output


def test_explicit_symlink_file_keeps_named_file_behavior(tmp_path) -> None:
    root = tmp_path / "book"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    target = external / "outside.md"
    link = root / "linked.md"
    config = tmp_path / "scieqlint.toml"
    target.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    link.symlink_to(target)
    config.write_text('[project]\nroot = "book"\n', encoding="utf-8")

    result = CliRunner().invoke(main, ["check", str(link), "--config", str(config)])

    assert result.exit_code == 1
    assert "ALG001" in result.output
    assert "linked.md" in result.output


def test_project_order_controls_cross_file_symbol_checks_without_paths(tmp_path) -> None:
    root = tmp_path / "book"
    root.mkdir()
    symbols = root / "z-symbols.md"
    appendix = root / "m-appendix.md"
    paper = root / "a-paper.md"
    ignored = root / "ignored.md"
    config = tmp_path / "scieqlint.toml"
    symbols.write_text("<!-- scieqlint-symbol: E = energy -->\n", encoding="utf-8")
    appendix.write_text("# Appendix\n", encoding="utf-8")
    paper.write_text("$$\nE = E\n$$\n", encoding="utf-8")
    ignored.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    config.write_text(
        "\n".join(
            [
                "[project]",
                'root = "book"',
                'order = ["z-symbols.md", "a-paper.md"]',
                "",
                "[checks.symbols]",
                "enabled = true",
                "",
                "[ignore]",
                'files = ["ignored.md"]',
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        main,
        ["check", "--config", str(config), "--format", "json"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["diagnostics"] == []
    assert payload["summary"]["files_checked"] == 2


def test_ignore_applies_to_project_order_entries_without_paths(tmp_path) -> None:
    root = tmp_path / "book"
    root.mkdir()
    ignored = root / "ignored.md"
    config = tmp_path / "scieqlint.toml"
    ignored.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    config.write_text(
        "\n".join(
            [
                "[project]",
                'root = "book"',
                'order = ["ignored.md"]',
                "",
                "[ignore]",
                'files = ["ignored.md"]',
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        main,
        ["check", "--config", str(config), "--format", "json"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["diagnostics"] == []
    assert payload["summary"]["files_checked"] == 0


def test_empty_project_order_preserves_no_path_current_directory_behavior(
    tmp_path,
    monkeypatch,
) -> None:
    book = tmp_path / "book"
    chapter = book / "chapter"
    chapter.mkdir(parents=True)
    (book / "scieqlint.toml").write_text('[project]\nroot = "."\norder = []\n', encoding="utf-8")
    (book / "outside.md").write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    (chapter / "inside.md").write_text("# clean\n", encoding="utf-8")
    monkeypatch.chdir(chapter)

    result = CliRunner().invoke(main, ["check", "--format", "json"])
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["summary"]["files_checked"] == 1
    assert payload["diagnostics"] == []


def test_project_absolute_root_controls_default_paths(tmp_path) -> None:
    root = tmp_path / "book"
    root.mkdir()
    doc = root / "paper.md"
    config = tmp_path / "scieqlint.toml"
    doc.write_text("# Paper\n", encoding="utf-8")
    config.write_text(
        f'[project]\nroot = "{root.resolve().as_posix()}"\norder = ["paper.md"]\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", "--config", str(config)])

    assert result.exit_code == 0
    assert "files checked: 1" in result.output


def test_project_ignore_can_match_absolute_discovered_paths_outside_root(tmp_path) -> None:
    root = tmp_path / "book"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    ignored = external / "ignored.md"
    config = tmp_path / "scieqlint.toml"
    ignored.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    config.write_text(
        "\n".join(
            [
                "[project]",
                'root = "book"',
                "",
                "[ignore]",
                f'files = ["{ignored.resolve().as_posix()}"]',
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(external), "--config", str(config)])

    assert result.exit_code == 0
    assert "files checked: 0" in result.output
