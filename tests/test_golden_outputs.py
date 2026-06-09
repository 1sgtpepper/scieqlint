from __future__ import annotations

import json
from importlib import resources
from pathlib import Path, PurePosixPath

from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource

from scieqlint.api import check_documents, check_paths, graph_paths
from scieqlint.config.model import Config, ReportConfig
from scieqlint.diag.model import CheckResult
from scieqlint.graph.json import render_graph_json
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.report.github import GitHubReporter
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter
from scieqlint.report.text import TextReporter

FIXTURE = Path("tests/fixtures/bad/famous_bad.md")
SUPPRESSED_FIXTURE = Path("tests/fixtures/bad/suppressed_bad.md")
GRAPH_FIXTURE = Path("tests/fixtures/good/graph_refs.md")


def test_text_golden_output_matches_famous_bad_fixture() -> None:
    result = check_paths([FIXTURE])

    assert TextReporter().render(result) == Path("tests/golden/text/famous_bad.txt").read_text(
        encoding="utf-8"
    )


def test_json_golden_output_matches_schema_and_famous_bad_fixture() -> None:
    rendered = JsonReporter().render(check_paths([FIXTURE]))
    schema = _schema("scieqlint-result-0.1.schema.json")
    diagnostic_schema = _schema("scieqlint-diagnostic-0.1.schema.json")
    registry = Registry().with_resources(
        [
            (schema["$id"], Resource.from_contents(schema)),
            (diagnostic_schema["$id"], Resource.from_contents(diagnostic_schema)),
        ]
    )

    Draft202012Validator(schema, registry=registry).validate(json.loads(rendered))
    assert rendered == Path("tests/golden/json/famous_bad.json").read_text(encoding="utf-8")


def test_json_golden_output_hides_suppressed_diagnostics_by_default() -> None:
    rendered = JsonReporter().render(check_paths([SUPPRESSED_FIXTURE]))
    _validate_json_result(rendered)

    assert rendered == Path("tests/golden/json/suppressed_hidden.json").read_text(encoding="utf-8")


def test_json_golden_output_includes_suppressed_diagnostics_when_enabled() -> None:
    document = SourceDocument.from_text(
        PurePosixPath(SUPPRESSED_FIXTURE.as_posix()),
        SUPPRESSED_FIXTURE.read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
    )
    result = _check_documents_with_report([document], show_suppressed=True)
    rendered = JsonReporter().render(result)
    _validate_json_result(rendered)

    assert rendered == Path("tests/golden/json/suppressed_visible.json").read_text(encoding="utf-8")


def test_github_golden_output_matches_famous_bad_fixture() -> None:
    result = check_paths([FIXTURE])

    assert GitHubReporter().render(result) == Path("tests/golden/github/famous_bad.txt").read_text(
        encoding="utf-8"
    )


def test_sarif_golden_output_matches_famous_bad_fixture() -> None:
    result = check_paths([FIXTURE])

    assert SarifReporter().render(result) == Path("tests/golden/sarif/famous_bad.sarif").read_text(
        encoding="utf-8"
    )


def test_graph_golden_output_matches_schema_and_fixture() -> None:
    rendered = render_graph_json(graph_paths([GRAPH_FIXTURE]))
    schema = _schema("scieqlint-graph-0.3.schema.json")

    Draft202012Validator(schema).validate(json.loads(rendered))
    assert rendered == Path("tests/golden/graph/graph_refs.json").read_text(encoding="utf-8")


def test_github_acceptance_example_emits_annotation_location_and_title() -> None:
    result = check_paths([Path("examples/bad/famous_bad.md")])

    assert GitHubReporter().render(result) == (
        "::error title=ALG001 algebraic identity does not hold,"
        "file=examples/bad/famous_bad.md,line=4,col=1,endLine=4,endColumn=19"
        "::left - right = 2*a*b\n"
    )


def _schema(name: str) -> dict[str, object]:
    return json.loads(
        resources.files("scieqlint.schemas").joinpath(name).read_text(encoding="utf-8")
    )


def _validate_json_result(rendered: str) -> None:
    schema = _schema("scieqlint-result-0.1.schema.json")
    diagnostic_schema = _schema("scieqlint-diagnostic-0.1.schema.json")
    registry = Registry().with_resources(
        [
            (schema["$id"], Resource.from_contents(schema)),
            (diagnostic_schema["$id"], Resource.from_contents(diagnostic_schema)),
        ]
    )
    Draft202012Validator(schema, registry=registry).validate(json.loads(rendered))


def _check_documents_with_report(
    documents: list[SourceDocument],
    *,
    show_suppressed: bool,
) -> CheckResult:
    return check_documents(
        documents,
        config=Config(report=ReportConfig(show_suppressed=show_suppressed)),
    )
