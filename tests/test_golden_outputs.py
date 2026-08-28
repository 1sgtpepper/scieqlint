from __future__ import annotations

import json
from importlib import resources
from pathlib import Path, PurePosixPath

from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource

from scieqlint.api import check_documents, check_paths, graph_paths
from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    ProfileConfig,
    ReportConfig,
)
from scieqlint.diag.model import CheckResult, SourceSpan
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.facts.reference import CrossrefMetadataFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.graph.json import render_graph_json
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost
from scieqlint.report.github import GitHubReporter
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter
from scieqlint.report.text import TextReporter

FIXTURE = Path("tests/fixtures/bad/famous_bad.md")
AMBIGUOUS_REFERENCE_FIXTURE = Path("tests/fixtures/bad/ambiguous_equation_reference.md")
SUPPRESSED_FIXTURE = Path("tests/fixtures/bad/suppressed_bad.md")
GRAPH_FIXTURE = Path("tests/fixtures/good/graph_refs.md")
CROSS_FORMAT_FIXTURE = Path("tests/fixtures/bad/cross_format_references.md")
NOTEBOOK_CROSSREF_BAD_FIXTURE = Path("tests/fixtures/bad/notebook_crossrefs_bad.ipynb")
NOTEBOOK_CROSSREF_GOOD_FIXTURE = Path("tests/fixtures/good/notebook_crossrefs_good.ipynb")


def test_text_golden_output_matches_famous_bad_fixture() -> None:
    result = check_paths([FIXTURE])

    assert TextReporter().render(result) == Path("tests/golden/text/famous_bad.txt").read_text(
        encoding="utf-8"
    )


def test_text_golden_output_matches_ambiguous_equation_reference_fixture() -> None:
    result = check_paths([AMBIGUOUS_REFERENCE_FIXTURE])

    assert TextReporter().render(result) == Path(
        "tests/golden/text/ambiguous_equation_reference.txt"
    ).read_text(encoding="utf-8")


def test_reference_fixture_reporters_preserve_ordered_diagnostic_contract() -> None:
    result = check_paths([AMBIGUOUS_REFERENCE_FIXTURE])

    json_result = json.loads(JsonReporter().render(result))
    assert [diagnostic["code"] for diagnostic in json_result["diagnostics"]] == [
        "REF001",
        "REF011",
    ]
    assert GitHubReporter().render(result).splitlines() == [
        (
            "::error title=REF001 duplicate equation label%3A shared,"
            "file=tests/fixtures/bad/ambiguous_equation_reference.md,line=4,col=11,"
            "endLine=4,endColumn=16::duplicate equation label: shared"
        ),
        (
            "::warning title=REF011 ambiguous equation reference%3A shared,"
            "file=tests/fixtures/bad/ambiguous_equation_reference.md,line=6,col=10,"
            "endLine=6,endColumn=15::reference text: {eq}`shared`"
        ),
    ]
    sarif_result = json.loads(SarifReporter().render(result))
    assert [item["ruleId"] for item in sarif_result["runs"][0]["results"]] == [
        "REF001",
        "REF011",
    ]


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


def test_cross_format_portability_output_matches_reporter_goldens() -> None:
    result = _cross_format_result()

    assert TextReporter().render(result) == Path(
        "tests/golden/text/cross_format_references.txt"
    ).read_text(encoding="utf-8")
    assert JsonReporter().render(result) == Path(
        "tests/golden/json/cross_format_references.json"
    ).read_text(encoding="utf-8")
    assert GitHubReporter().render(result) == Path(
        "tests/golden/github/cross_format_references.txt"
    ).read_text(encoding="utf-8")
    assert SarifReporter().render(result) == Path(
        "tests/golden/sarif/cross_format_references.sarif"
    ).read_text(encoding="utf-8")


def test_notebook_crossrefs_reporters_match_goldens_and_json_schema() -> None:
    result = _notebook_crossrefs_result()
    rendered_json = JsonReporter().render(result)

    _validate_json_result(rendered_json, version="0.2")
    assert TextReporter().render(result) == Path(
        "tests/golden/text/notebook_crossrefs_bad.txt"
    ).read_text(encoding="utf-8")
    assert rendered_json == Path("tests/golden/json/notebook_crossrefs_bad.json").read_text(
        encoding="utf-8"
    )
    assert GitHubReporter().render(result) == Path(
        "tests/golden/github/notebook_crossrefs_bad.txt"
    ).read_text(encoding="utf-8")
    assert SarifReporter().render(result) == Path(
        "tests/golden/sarif/notebook_crossrefs_bad.sarif"
    ).read_text(encoding="utf-8")


def test_notebook_crossrefs_bad_path_fixture_emits_each_conflict(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[profile]\nname = "notebook-crossrefs"\n', encoding="utf-8")

    result = check_paths(
        [NOTEBOOK_CROSSREF_BAD_FIXTURE],
        config_path=config_path,
    )

    assert [item.code for item in result.diagnostics] == ["PORT004", "PORT004", "PORT004"]


def test_notebook_crossrefs_good_path_fixture_is_quiet(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text('[profile]\nname = "notebook-crossrefs"\n', encoding="utf-8")

    result = check_paths([NOTEBOOK_CROSSREF_GOOD_FIXTURE], config_path=config_path)

    assert not any(item.code == "PORT004" for item in result.diagnostics)


def test_text_golden_output_matches_crossref_metadata_engine_path() -> None:
    assert TextReporter().render(_crossref_metadata_result()) == Path(
        "tests/golden/text/crossref_metadata.txt"
    ).read_text(encoding="utf-8")


def test_json_golden_output_matches_crossref_metadata_schema() -> None:
    rendered = JsonReporter().render(_crossref_metadata_result())
    schema = _schema("scieqlint-result-0.2.schema.json")
    diagnostic_schema = _schema("scieqlint-diagnostic-0.2.schema.json")
    registry = Registry().with_resources(
        [
            (schema["$id"], Resource.from_contents(schema)),
            (diagnostic_schema["$id"], Resource.from_contents(diagnostic_schema)),
        ]
    )

    Draft202012Validator(schema, registry=registry).validate(json.loads(rendered))
    assert rendered == Path("tests/golden/json/crossref_metadata.json").read_text(encoding="utf-8")


def test_github_golden_output_matches_crossref_metadata_engine_path() -> None:
    assert GitHubReporter().render(_crossref_metadata_result()) == Path(
        "tests/golden/github/crossref_metadata.txt"
    ).read_text(encoding="utf-8")


def test_sarif_golden_output_matches_crossref_metadata_engine_path() -> None:
    assert SarifReporter().render(_crossref_metadata_result()) == Path(
        "tests/golden/sarif/crossref_metadata.sarif"
    ).read_text(encoding="utf-8")


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


def _validate_json_result(rendered: str, *, version: str = "0.1") -> None:
    schema = _schema(f"scieqlint-result-{version}.schema.json")
    diagnostic_schema = _schema(f"scieqlint-diagnostic-{version}.schema.json")
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


def _cross_format_result() -> CheckResult:
    document = SourceDocument.from_text(
        PurePosixPath(CROSS_FORMAT_FIXTURE.as_posix()),
        CROSS_FORMAT_FIXTURE.read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
    )
    return check_documents(
        [document],
        config=Config(
            checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
            profile=ProfileConfig(
                name="cross-format-references",
                output_profile="commonmark",
            ),
        ),
    )


def _notebook_crossrefs_result() -> CheckResult:
    document = SourceDocument.from_text(
        PurePosixPath(NOTEBOOK_CROSSREF_BAD_FIXTURE.as_posix()),
        NOTEBOOK_CROSSREF_BAD_FIXTURE.read_text(encoding="utf-8"),
        DocumentKind.NOTEBOOK,
    )
    return check_documents(
        [document],
        config=Config(
            checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
            profile=ProfileConfig(name="notebook-crossrefs"),
        ),
    )


def _crossref_metadata_result() -> CheckResult:
    def fact(
        fact_id: str,
        *,
        document_id: str,
        boundary: str,
        source_format: str,
        kind: str,
        placement: str,
    ) -> CrossrefMetadataFact:
        fact_span = SourceSpan(
            path=PurePosixPath(document_id),
            start=0,
            end=1,
            line=1,
            col=1,
            end_line=1,
            end_col=1,
        )
        return CrossrefMetadataFact(
            fact_id=fact_id,
            document_id=document_id,
            span=fact_span,
            raw=None,
            source_fact_id=f"{fact_id}::source",
            logical_target="energy",
            normalized_target="energy",
            source_format=source_format,
            output_boundary=boundary,
            normalized_target_path=PurePosixPath("energy.md"),
            resolved_target_kind=kind,
            target_metadata=(("placement", placement),),
            metadata_kind="target-definition",
            target_span=fact_span,
        )

    metadata = (
        fact(
            "source-metadata",
            document_id="a-source.md",
            boundary="source.md",
            source_format="markdown",
            kind="heading",
            placement="before_heading",
        ),
        fact(
            "output-metadata",
            document_id="z-rendered.ipynb",
            boundary="rendered.ipynb#output-0",
            source_format="notebook",
            kind="figure",
            placement="before_block",
        ),
    )
    diagnostics = tuple(
        diagnostic.to_diagnostic()
        for diagnostic in ReferenceEngine().run(QueryHost(FactSnapshot(crossref_metadata=metadata)))
    )
    return CheckResult(
        diagnostics=diagnostics,
        files_checked=1,
        math_blocks_checked=0,
        config_path=None,
        version="1.1.0",
    )
