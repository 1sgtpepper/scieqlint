from __future__ import annotations

from importlib import resources


def test_py_typed_is_packaged() -> None:
    assert resources.files("scieqlint").joinpath("py.typed").is_file()


def test_schema_is_packaged() -> None:
    schema = resources.files("scieqlint.schemas").joinpath("scieqlint-result-0.1.schema.json")
    assert schema.is_file()
