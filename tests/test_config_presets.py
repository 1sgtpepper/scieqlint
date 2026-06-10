from __future__ import annotations

import pytest

from scieqlint.config.load import load_config
from scieqlint.config.presets import list_presets, read_preset_text


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


def test_load_config_rejects_unknown_preset() -> None:
    with pytest.raises(ValueError, match="unknown preset: unknown"):
        load_config(preset="unknown")


@pytest.mark.parametrize("preset", ["../mechanics", "mechanics.toml", "Mechanics"])
def test_load_config_rejects_invalid_preset_resource_names(preset: str) -> None:
    with pytest.raises(ValueError, match="unknown preset:"):
        load_config(preset=preset)


def test_preset_resources_are_listed_and_readable() -> None:
    assert list_presets() == ("mechanics",)
    assert "[vars]" in read_preset_text("mechanics")
