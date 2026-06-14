import json
from pathlib import Path, PurePosixPath
from typing import cast

import pytest

import scieqlint.compat.architecture_pipeline as architecture_pipeline
from scieqlint.api_architecture import analyze_paths_architecture
from scieqlint.compat.architecture_pipeline import analyze_documents_architecture
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.catalog_architecture import ARCHITECTURE_CATALOG, install_architecture_catalog
from scieqlint.engine.base import Engine
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.schema.json_architecture import render_analysis_result_json


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
