from __future__ import annotations

import json
from importlib import resources
from pathlib import Path, PurePosixPath

from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource

from scieqlint.api import check_documents
from scieqlint.config.model import Config, ProfileConfig, ProjectConfig
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.report.github import GitHubReporter
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter
from scieqlint.report.text import TextReporter

MARKDOWN_FIXTURE = Path("tests/fixtures/bad/code_cell_metadata.md")
NOTEBOOK_FIXTURE = Path("tests/fixtures/bad/code_cell_metadata.ipynb")
GOLDEN = Path("tests/golden/json/code_cell_metadata.json")
TEXT_GOLDEN = Path("tests/golden/text/code_cell_metadata.txt")
GITHUB_GOLDEN = Path("tests/golden/github/code_cell_metadata.txt")
SARIF_GOLDEN = Path("tests/golden/sarif/code_cell_metadata.sarif")


def test_code_cell_metadata_fixtures_match_reporter_goldens_and_schema() -> None:
    result = _check_fixtures()
    rendered_json = JsonReporter().render(result)

    _validate_json_result(rendered_json)
    assert rendered_json == GOLDEN.read_text(encoding="utf-8")
    assert TextReporter().render(result) == TEXT_GOLDEN.read_text(encoding="utf-8")
    assert GitHubReporter().render(result) == GITHUB_GOLDEN.read_text(encoding="utf-8")

    rendered_sarif = SarifReporter().render(result)
    assert json.loads(rendered_sarif)["version"] == "2.1.0"
    assert rendered_sarif == SARIF_GOLDEN.read_text(encoding="utf-8")


def _check_fixtures():
    documents = tuple(
        SourceDocument.from_text(
            PurePosixPath(path.as_posix()),
            path.read_text(encoding="utf-8"),
            DocumentKind.NOTEBOOK if path.suffix == ".ipynb" else DocumentKind.MARKDOWN,
        )
        for path in (MARKDOWN_FIXTURE, NOTEBOOK_FIXTURE)
    )
    return check_documents(
        documents,
        config=Config(
            profile=ProfileConfig(name="code-cell-metadata"),
            project=ProjectConfig(code_cell_languages=("python", "bash")),
        ),
    )


def _validate_json_result(rendered: str) -> None:
    result_schema = _schema("scieqlint-result-0.2.schema.json")
    diagnostic_schema = _schema("scieqlint-diagnostic-0.2.schema.json")
    registry = Registry().with_resources(
        [
            (result_schema["$id"], Resource.from_contents(result_schema)),
            (diagnostic_schema["$id"], Resource.from_contents(diagnostic_schema)),
        ]
    )
    Draft202012Validator(result_schema, registry=registry).validate(json.loads(rendered))


def _schema(name: str) -> dict[str, object]:
    return json.loads(
        resources.files("scieqlint.schemas").joinpath(name).read_text(encoding="utf-8")
    )
