from __future__ import annotations

import json
from importlib import resources

import pytest
from jsonschema import ValidationError
from jsonschema.validators import Draft202012Validator


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
    assert "suppression_reason" in schema["properties"]


def test_diagnostic_schema_requires_reason_for_suppressed_diagnostics() -> None:
    validator = Draft202012Validator(_diagnostic_schema())
    diagnostic = _diagnostic(suppressed=True)
    diagnostic["suppression_reason"] = "source comment"

    validator.validate(diagnostic)


def test_diagnostic_schema_rejects_suppressed_diagnostic_without_reason() -> None:
    validator = Draft202012Validator(_diagnostic_schema())

    with pytest.raises(ValidationError):
        validator.validate(_diagnostic(suppressed=True))


def test_diagnostic_schema_accepts_unsuppressed_diagnostic_without_reason() -> None:
    validator = Draft202012Validator(_diagnostic_schema())

    validator.validate(_diagnostic(suppressed=False))


def _diagnostic_schema() -> dict[str, object]:
    schema_text = (
        resources.files("scieqlint.schemas")
        .joinpath("scieqlint-diagnostic-0.1.schema.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(schema_text)


def _diagnostic(*, suppressed: bool) -> dict[str, object]:
    return {
        "cell": None,
        "cell_line": None,
        "code": "ALG001",
        "col": 1,
        "detail": "left - right = 2*a*b",
        "end_col": 19,
        "end_line": 1,
        "equation": "(a+b)^2 = a^2 + b^2",
        "hint": None,
        "line": 1,
        "message": "algebraic identity does not hold",
        "path": "paper.md",
        "severity": "error",
        "suppressed": suppressed,
    }


def test_graph_schema_is_valid_json_and_names_required_fields() -> None:
    schema_text = (
        resources.files("scieqlint.schemas")
        .joinpath("scieqlint-graph-0.3.schema.json")
        .read_text(encoding="utf-8")
    )
    schema = json.loads(schema_text)

    assert schema["$schema"].startswith("https://json-schema.org/")
    assert schema["required"] == ["schema_version", "nodes", "edges"]
    assert schema["properties"]["schema_version"]["const"] == "0.3"
