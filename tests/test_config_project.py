from __future__ import annotations

import pytest

from scieqlint.config.load import load_config


def test_load_config_accepts_check_toggles(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        "\n".join(
            [
                "[checks.algebra]",
                "enabled = false",
                "",
                "[checks.references]",
                "enabled = false",
                "",
                "[checks.symbols]",
                "enabled = true",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.checks.algebra.enabled is False
    assert config.checks.references.enabled is False
    assert config.checks.symbols.enabled is True


def test_load_config_accepts_ignore_files(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[ignore]\nfiles = ["examples/bad/**"]\n', encoding="utf-8")

    config = load_config(config_path)

    assert config.ignore.files == ("examples/bad/**",)


def test_load_config_accepts_report_show_suppressed(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text("[report]\nshow_suppressed = true\n", encoding="utf-8")

    config = load_config(config_path)

    assert config.report.show_suppressed is True


def test_load_config_accepts_project_order(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        '[project]\nroot = "book"\norder = ["symbols.md", "chapters/**/*.md"]\n',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.project.root.as_posix() == "book"
    assert config.project.order == ("symbols.md", "chapters/**/*.md")


def test_load_config_accepts_baseline_files(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[baseline]\nfiles = ["scieqlint-baseline.json"]\n', encoding="utf-8")

    config = load_config(config_path)

    assert config.baseline.files == ("scieqlint-baseline.json",)


def test_load_config_rejects_non_bool_report_show_suppressed(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[report]\nshow_suppressed = "yes"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="show_suppressed must be true or false"):
        load_config(config_path)


def test_load_config_rejects_non_bool_symbol_setting(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[checks.symbols]\nenabled = "yes"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="enabled must be true or false"):
        load_config(config_path)


def test_load_config_rejects_non_string_ignore_files(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text("[ignore]\nfiles = [1]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="files must be a list of strings"):
        load_config(config_path)


def test_load_config_rejects_non_string_project_order(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text("[project]\norder = [1]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="order must be a list of strings"):
        load_config(config_path)


def test_load_config_rejects_non_string_project_root(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text("[project]\nroot = 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="root must be a string"):
        load_config(config_path)


def test_load_config_rejects_non_string_baseline_files(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text("[baseline]\nfiles = [1]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="files must be a list of strings"):
        load_config(config_path)
