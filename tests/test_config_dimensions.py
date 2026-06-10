from __future__ import annotations

import pytest

from scieqlint.config.load import load_config
from scieqlint.config.model import DimensionConfig


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


def test_load_config_accepts_aliases_for_configured_vars(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        "\n".join(
            [
                "[vars]",
                'rho = "M L^-3"',
                'theta = "1"',
                "",
                "[aliases]",
                'rho = ["\\\\rho", "ρ"]',
                'theta = ["\\\\theta"]',
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert [(entry.canonical, entry.alias) for entry in config.aliases] == [
        ("rho", "\\rho"),
        ("rho", "ρ"),
        ("theta", "\\theta"),
    ]


def test_load_config_rejects_alias_for_unknown_var(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[aliases]\nrho = ["\\\\rho"]\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"\[aliases\].rho must reference a configured variable"):
        load_config(config_path)


def test_load_config_rejects_empty_alias_key(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[vars]\nrho = "M"\n[aliases]\n"" = ["\\\\rho"]\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"\[aliases\] keys must be non-empty strings"):
        load_config(config_path)


def test_load_config_rejects_non_list_aliases(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[vars]\nrho = "M"\n[aliases]\nrho = "\\\\rho"\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"\[aliases\].rho must be a list of strings"):
        load_config(config_path)


def test_load_config_rejects_empty_alias_values(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[vars]\nrho = "M"\n[aliases]\nrho = [""]\n', encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"\[aliases\].rho must be a list of non-empty strings",
    ):
        load_config(config_path)


def test_load_config_rejects_alias_collision_with_var(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        '[vars]\nrho = "M"\ntheta = "1"\n[aliases]\nrho = ["theta"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="alias collision: theta maps to both theta and rho"):
        load_config(config_path)


def test_load_config_rejects_alias_collision_between_aliases(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        '[vars]\nrho = "M"\ntheta = "1"\n[aliases]\nrho = ["x"]\ntheta = ["x"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="alias collision: x maps to both rho and theta"):
        load_config(config_path)


def test_load_config_rejects_invalid_dimension_expression(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[vars]\nbad = "Q"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="unknown base dimension: Q"):
        load_config(config_path)


def test_load_config_rejects_empty_dimension_expression(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[vars]\nempty = ""\n', encoding="utf-8")

    with pytest.raises(ValueError, match="dimension expression must not be empty"):
        load_config(config_path)


def test_load_config_rejects_missing_dimension_power(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[vars]\nbad = "M^"\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"dimension power is missing: M\^"):
        load_config(config_path)


def test_load_config_rejects_non_integer_dimension_power(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[vars]\nbad = "M^x"\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"dimension power must be an integer: M\^x"):
        load_config(config_path)


def test_load_config_rejects_invalid_dimension_mode(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[checks.dimension]\nmode = "always"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="mode must be auto, on, or off"):
        load_config(config_path)


def test_load_config_rejects_non_string_dimension_mode(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text("[checks.dimension]\nmode = true\n", encoding="utf-8")

    with pytest.raises(ValueError, match="mode must be auto, on, or off"):
        load_config(config_path)


def test_load_config_rejects_invalid_unknown_variable_policy(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[checks.dimension]\nunknown_variables = "error"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="unknown_variables must be warn or ignore"):
        load_config(config_path)


def test_load_config_rejects_non_string_var_dimension(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text("[vars]\nm = 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"\[vars\].m must be a dimension string"):
        load_config(config_path)


def test_dimension_config_auto_is_quiet_without_vars() -> None:
    config = DimensionConfig(mode="auto")

    assert config.is_active(has_vars=False) is False
    assert config.is_active(has_vars=True) is True


def test_dimension_config_on_and_off_are_explicit() -> None:
    assert DimensionConfig(mode="on").is_active(has_vars=False) is True
    assert DimensionConfig(mode="off").is_active(has_vars=True) is False
