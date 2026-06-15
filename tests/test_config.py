from __future__ import annotations

import pytest

from scieqlint.config.load import load_config
from scieqlint.config.model import DimensionConfig
from scieqlint.config.presets import list_presets, read_preset_text


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


def test_load_config_applies_packaged_preset_without_user_config(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_config(preset="mechanics")

    assert config.path is None
    assert config.checks.dimension.mode == "on"
    assert {entry.name: entry.dimension.exponents for entry in config.vars}["F"] == (
        1,
        1,
        -2,
        0,
        0,
        0,
        0,
    )


def test_load_config_user_config_overrides_preset_values(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        "\n".join(
            [
                "[checks.dimension]",
                'unknown_variables = "ignore"',
                "",
                "[vars]",
                'F = "M"',
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path, preset="mechanics")

    assert config.checks.dimension.mode == "on"
    assert config.checks.dimension.unknown_variables == "ignore"
    assert {entry.name: entry.dimension.exponents for entry in config.vars}["F"] == (
        1,
        0,
        0,
        0,
        0,
        0,
        0,
    )


def test_generated_myst_preset_enables_generated_markdown_checks(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_config(preset="generated-myst")

    assert config.scanner.markdown is True
    assert config.scanner.inline_math is True
    assert config.scanner.math_fences is True
    assert config.parser.strict_unknowns is True
    assert config.checks.algebra.enabled is True
    assert config.checks.references.enabled is True
    assert config.checks.dimension.mode == "auto"


def test_load_config_user_config_overrides_generated_myst_strictness(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        "\n".join(
            [
                "[scanner]",
                "inline_math = false",
                "",
                "[parser]",
                "strict_unknowns = false",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path, preset="generated-myst")

    assert config.scanner.inline_math is False
    assert config.parser.strict_unknowns is False


def test_load_config_rejects_unknown_preset() -> None:
    with pytest.raises(ValueError, match="unknown preset: unknown"):
        load_config(preset="unknown")


@pytest.mark.parametrize("preset", ["../mechanics", "mechanics.toml", "Mechanics"])
def test_load_config_rejects_invalid_preset_resource_names(preset: str) -> None:
    with pytest.raises(ValueError, match="unknown preset:"):
        load_config(preset=preset)


def test_preset_resources_are_listed_and_readable() -> None:
    assert list_presets() == ("generated-myst", "mechanics")
    assert "[parser]" in read_preset_text("generated-myst")
    assert "[vars]" in read_preset_text("mechanics")


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


def test_load_config_rejects_non_bool_parser_strict_unknowns(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[parser]\nstrict_unknowns = "yes"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="strict_unknowns must be true or false"):
        load_config(config_path)


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
