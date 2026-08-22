from __future__ import annotations

import json
from importlib import resources
from pathlib import Path, PurePosixPath

from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource

from scieqlint.app import check_documents
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.report.github import GitHubReporter
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter
from scieqlint.report.text import TextReporter

FIXTURE = Path("tests/fixtures/generated/equation_like_text.md")


def test_generated_equation_like_text_fixture_matches_all_reporter_goldens() -> None:
    result = _check_fixture()

    assert [
        (
            diagnostic.code,
            diagnostic.span.line if diagnostic.span is not None else None,
            diagnostic.detail,
        )
        for diagnostic in result.diagnostics
    ] == [
        (
            "GEN005",
            5,
            "equation-like text was emitted outside a math container: 'F(x) = x + 1'",
        )
    ]

    rendered_json = JsonReporter().render(result)
    _validate_json_result(rendered_json)
    assert TextReporter().render(result) == Path(
        "tests/golden/text/generated_equation_like_text.txt"
    ).read_text(encoding="utf-8")
    assert rendered_json == Path("tests/golden/json/generated_equation_like_text.json").read_text(
        encoding="utf-8"
    )
    assert GitHubReporter().render(result) == Path(
        "tests/golden/github/generated_equation_like_text.txt"
    ).read_text(encoding="utf-8")
    assert SarifReporter().render(result) == Path(
        "tests/golden/sarif/generated_equation_like_text.sarif"
    ).read_text(encoding="utf-8")


def _check_fixture():
    document = SourceDocument.from_text(
        PurePosixPath(FIXTURE.as_posix()),
        FIXTURE.read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(source_document_id="source/equation_like_text.pdf"),
    )
    return check_documents(
        (document,),
        config=Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="pdf",
                conversion_stage="pdf-to-markdown",
            )
        ),
    )


def _schema(name: str) -> dict[str, object]:
    return json.loads(
        resources.files("scieqlint.schemas").joinpath(name).read_text(encoding="utf-8")
    )


def _validate_json_result(rendered: str) -> None:
    schema = _schema("scieqlint-result-0.2.schema.json")
    diagnostic_schema = _schema("scieqlint-diagnostic-0.2.schema.json")
    registry = Registry().with_resources(
        [
            (schema["$id"], Resource.from_contents(schema)),
            (diagnostic_schema["$id"], Resource.from_contents(diagnostic_schema)),
        ]
    )
    Draft202012Validator(schema, registry=registry).validate(json.loads(rendered))
