from __future__ import annotations

import json
from importlib import resources

import pytest
from jsonschema import ValidationError
from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource

from scieqlint.diag.model import CheckResult, Diagnostic, Severity
from scieqlint.report.json import JsonReporter


@pytest.mark.parametrize("version", ["0.1", "0.2"])
def test_result_schemas_are_valid_json_and_name_required_fields(version: str) -> None:
    schema_text = (
        resources.files("scieqlint.schemas")
        .joinpath(f"scieqlint-result-{version}.schema.json")
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


@pytest.mark.parametrize("version", ["0.1", "0.2"])
def test_diagnostic_schemas_are_valid_json_and_require_location_fields(version: str) -> None:
    schema_text = (
        resources.files("scieqlint.schemas")
        .joinpath(f"scieqlint-diagnostic-{version}.schema.json")
        .read_text(encoding="utf-8")
    )
    schema = json.loads(schema_text)
    for field in ["path", "line", "col", "end_line", "end_col"]:
        assert field in schema["required"]
    assert "suppression_reason" in schema["properties"]


def test_provenance_json_uses_0_2_and_is_rejected_by_preserved_0_1_schema() -> None:
    result = CheckResult(
        diagnostics=(
            Diagnostic(
                code="GEN001",
                severity=Severity.WARNING,
                message="generated output is missing preserved source anchor",
                span=None,
                profile="generated-myst",
                provenance_ids=("origin",),
                properties=(("source_document", "source/paper.md"),),
            ),
        ),
        files_checked=1,
        math_blocks_checked=0,
        config_path=None,
        version="1.1.0",
    )
    payload = json.loads(JsonReporter().render(result))

    assert payload["schema_version"] == "0.2"
    _result_validator("0.2").validate(payload)
    with pytest.raises(ValidationError):
        _result_validator("0.1").validate(payload)
    with pytest.raises(ValidationError):
        Draft202012Validator(_diagnostic_schema()).validate(payload["diagnostics"][0])


@pytest.mark.parametrize(
    ("profile", "provenance_ids", "properties"),
    [
        ("generated-myst", (), ()),
        (None, ("origin",), ()),
        (None, (), (("source_document", "source/paper.md"),)),
    ],
)
def test_each_projection_metadata_field_selects_json_schema_0_2(
    profile: str | None,
    provenance_ids: tuple[str, ...],
    properties: tuple[tuple[str, str], ...],
) -> None:
    result = CheckResult(
        diagnostics=(
            Diagnostic(
                code="GEN001",
                severity=Severity.WARNING,
                message="generated output diagnostic",
                span=None,
                profile=profile,
                provenance_ids=provenance_ids,
                properties=properties,
            ),
        ),
        files_checked=1,
        math_blocks_checked=0,
        config_path=None,
        version="1.1.0",
    )

    assert json.loads(JsonReporter().render(result))["schema_version"] == "0.2"


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


def _result_validator(version: str) -> Draft202012Validator:
    result_schema = _schema(f"scieqlint-result-{version}.schema.json")
    diagnostic_schema = _schema(f"scieqlint-diagnostic-{version}.schema.json")
    registry = Registry().with_resources(
        [(diagnostic_schema["$id"], Resource.from_contents(diagnostic_schema))]
    )
    return Draft202012Validator(result_schema, registry=registry)


def _schema(name: str) -> dict[str, object]:
    schema_text = resources.files("scieqlint.schemas").joinpath(name).read_text(encoding="utf-8")
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
