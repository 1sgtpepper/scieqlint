import json
from pathlib import Path, PurePosixPath
from typing import cast

import pytest

import scieqlint.compat.architecture_pipeline as architecture_pipeline
from scieqlint.api import check_paths
from scieqlint.api_architecture import analyze_paths_architecture, apply_config_policy_architecture
from scieqlint.compat.architecture_pipeline import analyze_documents_architecture
from scieqlint.config.model import BaselineConfig, Config, ProjectConfig
from scieqlint.diag.catalog import CATALOG, explain_code
from scieqlint.diag.catalog_architecture import ARCHITECTURE_CATALOG, install_architecture_catalog
from scieqlint.diag.model import Diagnostic, Severity, SourceSpan
from scieqlint.engine.base import Engine
from scieqlint.facts.math import DisplayMathFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.schema.json_architecture import render_analysis_result_json
from scieqlint.schema.result import AnalysisResult

ARCHITECTURE_BAD_FIXTURE = Path("tests/fixtures/bad/architecture_myst_bad.md")
ARCHITECTURE_BAD_GOLDEN = Path("tests/golden/json/architecture_myst_bad.json")


def test_architecture_api_loads_paths_and_renders_json(tmp_path: Path):
    source = tmp_path / "lecture.md"
    source.write_text("####Title\n", encoding="utf-8")
    result = analyze_paths_architecture((source,), profiles=("scientific-myst",))
    rendered = render_analysis_result_json(result)
    assert "STR001" in rendered
    assert '"schema_version": "0.2-architecture-preview"' in rendered


def test_architecture_api_discovers_supported_files_in_directories(tmp_path: Path):
    nested = tmp_path / "notes"
    nested.mkdir()
    (tmp_path / "lecture.md").write_text("# Lecture\n", encoding="utf-8")
    (nested / "chapter.qmd").write_text("## Chapter\n", encoding="utf-8")
    (nested / "ignore.txt").write_text("# Not loaded\n", encoding="utf-8")

    result = analyze_paths_architecture((tmp_path,))

    assert result.summary()["files_checked"] == 2
    assert {document.path.name for document in result.snapshot.documents} == {
        "chapter.qmd",
        "lecture.md",
    }


def test_architecture_api_ignores_unsupported_explicit_files(tmp_path: Path):
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("# Not loaded\n", encoding="utf-8")

    result = analyze_paths_architecture((unsupported,))

    assert result.summary()["files_checked"] == 0
    assert result.snapshot.documents == ()


def test_architecture_pipeline_skips_profile_engines_without_registered_runner(
    monkeypatch: pytest.MonkeyPatch,
):
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "####Title\n",
        DocumentKind.MARKDOWN,
    )
    monkeypatch.setitem(architecture_pipeline._ENGINES, "structure", cast(Engine, None))

    result = analyze_documents_architecture((document,), profiles=("scientific-myst",))

    assert "STR001" not in {diagnostic.code for diagnostic in result.diagnostics}


def test_architecture_json_renders_diagnostics_and_catalog_entries(tmp_path: Path):
    source = tmp_path / "lecture.md"
    source.write_text("See {ref}`missing`.\n", encoding="utf-8")
    result = analyze_paths_architecture((source,), profiles=("scientific-myst",))

    rendered = json.loads(render_analysis_result_json(result))
    install_architecture_catalog()

    assert rendered["diagnostics"][0]["path"].endswith("lecture.md")
    assert rendered["diagnostics"][0]["detail"] == "{ref}`missing`"
    assert set(ARCHITECTURE_CATALOG) <= set(CATALOG)
    assert CATALOG["REF011"].message == "generic reference target not found"


def test_architecture_json_golden_output_matches_myst_fixture():
    rendered = render_analysis_result_json(
        analyze_paths_architecture((ARCHITECTURE_BAD_FIXTURE,), profiles=("scientific-myst",))
    )

    assert rendered == ARCHITECTURE_BAD_GOLDEN.read_text(encoding="utf-8")


def test_architecture_catalog_installs_all_preview_codes_for_explain_output():
    install_architecture_catalog()

    for code, info in ARCHITECTURE_CATALOG.items():
        assert CATALOG[code] == info
        explanation = explain_code(code)
        assert explanation is not None
        assert f"Message: {info.message}" in explanation


def test_stable_scan001_and_architecture_str002_are_separate(tmp_path: Path):
    source = tmp_path / "lecture.md"
    source.write_text("```{math}\na = a\n", encoding="utf-8")

    stable_result = check_paths([source])
    architecture_result = analyze_paths_architecture((source,), profiles=("scientific-myst",))

    assert [diagnostic.code for diagnostic in stable_result.diagnostics] == ["SCAN001"]
    assert [diagnostic.code for diagnostic in architecture_result.diagnostics] == ["STR002"]


def test_architecture_policy_suppresses_fenced_math_with_spanless_fact_present() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "<!-- scieqlint-disable-next-line ALG001 -->\n```{math}\n(a+b)^2 = a^2 + b^2\n```\n",
        DocumentKind.MARKDOWN,
    )
    diagnostic = _diagnostic(span=_span(line=3, col=1, end_line=3, end_col=20))
    result = AnalysisResult(
        snapshot=FactSnapshot(
            documents=(document,),
            display_math=(
                DisplayMathFact(
                    fact_id="display:spanless",
                    document_id="lecture.md",
                    span=None,
                    body="ignored",
                    container="dollar-dollar",
                ),
                DisplayMathFact(
                    fact_id="display:fenced",
                    document_id="lecture.md",
                    span=_span(start=43, end=73, line=2, col=1, end_line=4, end_col=3),
                    body="(a+b)^2 = a^2 + b^2",
                    container="fenced-math",
                ),
            ),
        ),
        diagnostics=(diagnostic,),
        profiles=("generated",),
    )

    policy_result = apply_config_policy_architecture(result, Config())

    assert policy_result.diagnostics[0].suppressed is True
    assert policy_result.diagnostics[0].suppression_reason == "source comment"


def test_architecture_policy_resolves_relative_baseline_without_config_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = tmp_path / "scieqlint-baseline.json"
    baseline.write_text(json.dumps({"diagnostics": [_baseline_entry()]}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = _analysis_result_with_diagnostic()

    policy_result = apply_config_policy_architecture(
        result,
        Config(baseline=BaselineConfig(files=("scieqlint-baseline.json",))),
    )

    assert policy_result.diagnostics[0].suppressed is True
    assert policy_result.diagnostics[0].suppression_reason == "baseline"


def test_architecture_policy_resolves_relative_baseline_from_absolute_project_root(
    tmp_path: Path,
) -> None:
    project = tmp_path / "book"
    project.mkdir()
    baseline = project / "scieqlint-baseline.json"
    baseline.write_text(json.dumps({"diagnostics": [_baseline_entry()]}), encoding="utf-8")
    result = _analysis_result_with_diagnostic()

    policy_result = apply_config_policy_architecture(
        result,
        Config(
            project=ProjectConfig(root=PurePosixPath(project.as_posix())),
            baseline=BaselineConfig(files=("scieqlint-baseline.json",)),
        ),
    )

    assert policy_result.diagnostics[0].suppressed is True
    assert policy_result.diagnostics[0].suppression_reason == "baseline"


def test_architecture_policy_accepts_absolute_baseline_file(tmp_path: Path) -> None:
    baseline = tmp_path / "scieqlint-baseline.json"
    baseline.write_text(json.dumps({"diagnostics": [_baseline_entry()]}), encoding="utf-8")
    result = _analysis_result_with_diagnostic()

    policy_result = apply_config_policy_architecture(
        result,
        Config(baseline=BaselineConfig(files=(baseline.as_posix(),))),
    )

    assert policy_result.diagnostics[0].suppressed is True
    assert policy_result.diagnostics[0].suppression_reason == "baseline"


def _analysis_result_with_diagnostic() -> AnalysisResult:
    return AnalysisResult(
        snapshot=FactSnapshot(),
        diagnostics=(_diagnostic(span=_span()),),
        profiles=("generated",),
    )


def _diagnostic(*, span: SourceSpan) -> Diagnostic:
    return Diagnostic(
        code="ALG001",
        severity=Severity.ERROR,
        message="algebraic identity does not hold",
        span=span,
        detail="left - right = 2*a*b",
    )


def _baseline_entry() -> dict[str, object]:
    return {
        "code": "ALG001",
        "path": "lecture.md",
        "line": 2,
        "col": 1,
        "end_line": 2,
        "end_col": 19,
        "detail": "left - right = 2*a*b",
    }


def _span(
    *,
    start: int = 3,
    end: int = 12,
    line: int = 2,
    col: int = 1,
    end_line: int = 2,
    end_col: int = 19,
) -> SourceSpan:
    return SourceSpan(
        path=PurePosixPath("lecture.md"),
        start=start,
        end=end,
        line=line,
        col=col,
        end_line=end_line,
        end_col=end_col,
    )
