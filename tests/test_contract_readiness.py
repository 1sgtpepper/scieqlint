from __future__ import annotations

import inspect
import json
import re
from importlib import resources
from pathlib import Path

import scieqlint.api as api
from scieqlint.cli import main
from scieqlint.diag.catalog import CATALOG, explain_code


def test_v100_public_api_contract_matches_docs() -> None:
    api_doc = Path("docs/api.md").read_text(encoding="utf-8")
    expected_exports = [
        "check_documents",
        "check_paths",
        "graph_documents",
        "graph_paths",
        "load_config",
    ]

    assert api.__all__ == expected_exports
    for name in expected_exports:
        assert name in api_doc

    assert str(inspect.signature(api.check_paths)) == (
        "(paths: 'Sequence[Path | str]', *, config_path: 'Path | str | None' = None, "
        "no_algebra: 'bool' = False, inline_math: 'bool' = False, "
        "strict_unknowns: 'bool' = False, absolute_paths: 'bool' = False) -> 'CheckResult'"
    )
    assert str(inspect.signature(api.check_documents)) == (
        "(documents: 'Sequence[SourceDocument]', *, config: 'Config') -> 'CheckResult'"
    )
    assert str(inspect.signature(api.graph_paths)) == (
        "(paths: 'Sequence[Path | str]', *, config_path: 'Path | str | None' = None) -> 'Graph'"
    )
    assert str(inspect.signature(api.graph_documents)) == (
        "(documents: 'Sequence[SourceDocument]', *, config: 'Config') -> 'Graph'"
    )


def test_v100_cli_contract_names_documented_commands() -> None:
    readiness = Path("docs/releases/v1.0.0-contract-readiness.md").read_text(encoding="utf-8")

    assert sorted(main.commands) == ["check", "demo", "explain", "graph", "init", "presets"]
    for command in ["check", "init", "demo", "explain", "presets", "graph"]:
        assert command in readiness


def test_v100_schema_contract_resources_and_versions_are_stable() -> None:
    schema_names = {
        "scieqlint-diagnostic-0.1.schema.json",
        "scieqlint-graph-0.3.schema.json",
        "scieqlint-result-0.1.schema.json",
    }
    packaged = {
        child.name
        for child in resources.files("scieqlint.schemas").iterdir()
        if child.name.endswith(".schema.json")
    }

    assert schema_names <= packaged
    assert (
        _schema("scieqlint-result-0.1.schema.json")["properties"]["schema_version"]["const"]
        == "0.1"
    )
    assert (
        _schema("scieqlint-graph-0.3.schema.json")["properties"]["schema_version"]["const"] == "0.3"
    )


def test_v100_documented_diagnostic_codes_exist_in_catalog() -> None:
    diagnostics_doc = Path("docs/diagnostics.md").read_text(encoding="utf-8")
    documented_codes = set(re.findall(r"`([A-Z]+[0-9]{3})`", diagnostics_doc))

    assert documented_codes
    assert documented_codes <= CATALOG.keys()
    for code in sorted(documented_codes):
        assert explain_code(code) is not None


def test_v100_contract_readiness_marks_remote_ci_gates_checked_after_main_is_green() -> None:
    readiness = Path("docs/releases/v1.0.0-contract-readiness.md").read_text(encoding="utf-8")

    for gate in [
        "GitHub CI quality job",
        "GitHub CI Python 3.11, 3.12, and 3.13 test matrix",
        "GitHub CI package build",
        "GitHub CI docs job",
    ]:
        assert f"- [x] {gate}" in readiness


def _schema(name: str) -> dict[str, object]:
    return json.loads(resources.files("scieqlint.schemas").joinpath(name).read_text())
