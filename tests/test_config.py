from __future__ import annotations

import pytest

from scieqlint.config.load import load_config
from scieqlint.config.model import DimensionConfig


def test_load_config_records_explicit_path(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text("[scanner]\nmarkdown = true\n", encoding="utf-8")
    config = load_config(config_path)
    assert config.path is not None
    assert config.path.as_posix().endswith("scieqlint.toml")


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


def test_load_config_accepts_check_toggles(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        "[checks.algebra]\nenabled = false\n\n[checks.references]\nenabled = false\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.checks.algebra.enabled is False
    assert config.checks.references.enabled is False


def test_load_config_accepts_ignore_files(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[ignore]\nfiles = ["examples/bad/**"]\n', encoding="utf-8")

    config = load_config(config_path)

    assert config.ignore.files == ("examples/bad/**",)


def test_load_config_accepts_dimension_settings_and_vars(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        "\n".join(
            [
                "[checks.dimension]",
                'mode = "on"',
                'unknown_variables = "ignore"',
                "",
                "[vars]",
                'theta = "1"',
                'm = "M"',
                'v = "L T^-1"',
                'E = "M L^2 T^-2"',
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.checks.dimension.mode == "on"
    assert config.checks.dimension.unknown_variables == "ignore"
    assert [(entry.name, entry.dimension.exponents) for entry in config.vars] == [
        ("E", (1, 2, -2, 0, 0, 0, 0)),
        ("m", (1, 0, 0, 0, 0, 0, 0)),
        ("theta", (0, 0, 0, 0, 0, 0, 0)),
        ("v", (0, 1, -1, 0, 0, 0, 0)),
    ]


def test_load_config_rejects_invalid_dimension_expression(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[vars]\nbad = "Q"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="unknown base dimension: Q"):
        load_config(config_path)


def test_load_config_rejects_invalid_dimension_mode(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[checks.dimension]\nmode = "always"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="mode must be auto, on, or off"):
        load_config(config_path)


def test_dimension_config_auto_is_quiet_without_vars() -> None:
    config = DimensionConfig(mode="auto")

    assert config.is_active(has_vars=False) is False
    assert config.is_active(has_vars=True) is True


def test_dimension_config_on_and_off_are_explicit() -> None:
    assert DimensionConfig(mode="on").is_active(has_vars=False) is True
    assert DimensionConfig(mode="off").is_active(has_vars=True) is False
