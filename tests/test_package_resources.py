from __future__ import annotations

from importlib import resources


def test_py_typed_is_packaged() -> None:
    assert resources.files("scieqlint").joinpath("py.typed").is_file()


def test_schema_is_packaged() -> None:
    schema = resources.files("scieqlint.schemas").joinpath("scieqlint-result-0.1.schema.json")
    assert schema.is_file()


def test_preset_is_packaged() -> None:
    preset = resources.files("scieqlint.presets").joinpath("mechanics.toml")
    assert preset.is_file()


def test_graph_schema_is_packaged() -> None:
    schema = resources.files("scieqlint.schemas").joinpath("scieqlint-graph-0.3.schema.json")
    assert schema.is_file()
