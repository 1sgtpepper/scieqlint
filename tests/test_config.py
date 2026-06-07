from __future__ import annotations

from scieqlint.config.load import load_config


def test_load_config_records_explicit_path(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text("[scanner]\nmarkdown = true\n", encoding="utf-8")
    config = load_config(config_path)
    assert config.path is not None
    assert config.path.as_posix().endswith("scieqlint.toml")


def test_load_config_finds_default_file_in_current_directory(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        "[scanner]\nmath_fences = false\n\n"
        "[checks.references]\nmissing_label_strict = true\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.path is not None
    assert config.path.as_posix().endswith("scieqlint.toml")
    assert config.scanner.math_fences is False
    assert config.checks.references.missing_label_strict is True


def test_load_config_accepts_check_toggles(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        "[checks.algebra]\nenabled = false\n\n"
        "[checks.references]\nenabled = false\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.checks.algebra.enabled is False
    assert config.checks.references.enabled is False
