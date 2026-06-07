from __future__ import annotations

import json
from importlib import resources


def test_result_schema_is_valid_json_and_names_required_fields() -> None:
    schema_text = (
        resources.files("scieqlint.schemas")
        .joinpath("scieqlint-result-0.1.schema.json")
        .read_text(encoding="utf-8")
    )
    schema = json.loads(schema_text)
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert schema["required"] == [
        "schema_version",
        "tool",
        "version",
        "summary",
        "diagnostics",
    ]


def test_diagnostic_schema_is_valid_json_and_requires_location_fields() -> None:
    schema_text = (
        resources.files("scieqlint.schemas")
        .joinpath("scieqlint-diagnostic-0.1.schema.json")
        .read_text(encoding="utf-8")
    )
    schema = json.loads(schema_text)
    for field in ["path", "line", "col", "end_line", "end_col"]:
        assert field in schema["required"]
