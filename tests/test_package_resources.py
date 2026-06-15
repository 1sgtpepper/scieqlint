from __future__ import annotations

from importlib import resources


def test_py_typed_is_packaged() -> None:
    assert resources.files("scieqlint").joinpath("py.typed").is_file()


def test_schema_is_packaged() -> None:
    schema = resources.files("scieqlint.schemas").joinpath("scieqlint-result-0.1.schema.json")
    assert schema.is_file()


def test_presets_are_packaged() -> None:
    presets = resources.files("scieqlint.presets")
    assert presets.joinpath("generated-myst.toml").is_file()
    assert presets.joinpath("mechanics.toml").is_file()


def test_graph_schema_is_packaged() -> None:
    schema = resources.files("scieqlint.schemas").joinpath("scieqlint-graph-0.3.schema.json")
    assert schema.is_file()
