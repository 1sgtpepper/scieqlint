from __future__ import annotations

import pytest

from scieqlint.config.load import load_config


def test_load_config_records_explicit_path(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text("[scanner]\nmarkdown = true\n", encoding="utf-8")
    config = load_config(config_path)
    assert config.path is not None
    assert config.path.as_posix().endswith("scieqlint.toml")


def test_load_config_uses_defaults_when_no_default_file_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.path is None
    assert config.scanner.markdown is True


def test_load_config_rejects_missing_explicit_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="config not found"):
        load_config(tmp_path / "missing.toml")


def test_load_config_finds_default_file_in_current_directory(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        "[scanner]\nmath_fences = false\n\n[checks.references]\nmissing_label_strict = true\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.path is not None
    assert config.path.as_posix().endswith("scieqlint.toml")
    assert config.scanner.math_fences is False
    assert config.checks.references.missing_label_strict is True


def test_load_config_rejects_non_table_sections(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('scanner = "enabled"\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"\[scanner\] must be a table"):
        load_config(config_path)


def test_load_config_rejects_non_bool_scanner_settings(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[scanner]\nmarkdown = "yes"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="markdown must be true or false"):
        load_config(config_path)
