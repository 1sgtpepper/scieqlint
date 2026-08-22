from __future__ import annotations

import json
from importlib import resources
from pathlib import Path, PurePosixPath

from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource

from scieqlint.api import check_documents
from scieqlint.config.model import Config, ProfileConfig, ScannerConfig
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.report.json import JsonReporter
from scieqlint.report.text import TextReporter

BAD_FIXTURE = Path("tests/fixtures/generated/formula_quality_bad.md")
GOOD_FIXTURE = Path("tests/fixtures/generated/formula_quality_good.md")


def test_generated_formula_quality_fixture_matches_text_and_json_goldens() -> None:
    result = _check_fixture(BAD_FIXTURE)
    rendered_json = JsonReporter().render(result)

    _validate_json_result(rendered_json)
    assert [
        (diagnostic.code, diagnostic.span.line if diagnostic.span else None, diagnostic.detail)
        for diagnostic in result.diagnostics
    ] == [
        ("GEN002", 3, "spaced-token artifact: 'A t t e n t'"),
        ("GEN002", 5, "garbled-marker artifact: '/C0 apod'"),
        ("GEN004", 7, "formula-not-decoded marker remains in generated output"),
        (
            "GEN003",
            9,
            "standalone \\[...\\] display delimiters are not portable generated Markdown",
        ),
        ("GEN005", 13, "equation-like text was emitted outside a math container: 'P = IV'"),
        ("GEN004", 15, "standalone formula image remains in generated output"),
    ]
    assert TextReporter().render(result) == Path(
        "tests/golden/text/generated_formula_quality.txt"
    ).read_text(encoding="utf-8")
    assert rendered_json == Path("tests/golden/json/generated_formula_quality.json").read_text(
        encoding="utf-8"
    )


def test_generated_formula_quality_negative_fixture_is_quiet() -> None:
    result = _check_fixture(GOOD_FIXTURE)

    assert (
        tuple(diagnostic for diagnostic in result.diagnostics if diagnostic.code.startswith("GEN"))
        == ()
    )


def _check_fixture(path: Path):
    document = SourceDocument.from_text(
        PurePosixPath(path.as_posix()),
        path.read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(source_document_id="source/formula_quality.pdf"),
    )
    return check_documents(
        (document,),
        config=Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="pdf",
                conversion_stage="pdf-to-markdown",
            ),
            scanner=ScannerConfig(inline_math=True),
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
