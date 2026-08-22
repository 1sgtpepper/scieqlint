from __future__ import annotations

from dataclasses import replace
from pathlib import PurePosixPath

from scieqlint.app import check_documents, check_paths
from scieqlint.config.load import load_config
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.config.presets import read_preset_text
from scieqlint.engine.generated import GeneratedOutputEngine
from scieqlint.facts.generated import GeneratedProvenanceFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.query.host import QueryHost


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def snapshot_for_translation(generated_text: str) -> FactSnapshot:
    source = doc(
        "source/lecture.md",
        "(jax_at_workaround)=\n## A Workaround\n\n(not_preserved)=\n## Other\n\nText.\n",
    )
    generated = doc("translated/lecture.md", generated_text)
    snapshot = MySTFrontend().lower((source, generated))
    provenance = GeneratedProvenanceFact(
        fact_id="translation-1",
        document_id=generated.path.as_posix(),
        span=None,
        source_document_id=source.path.as_posix(),
        generated_document_id=generated.path.as_posix(),
        tool="translation",
        preserved_anchor_inventory=("jax_at_workaround",),
    )
    return replace(snapshot, generated_provenance=(provenance,))


def test_generated_output_engine_reports_preserved_source_anchor_dropped_before_heading():
    snapshot = snapshot_for_translation("## A Workaround\n\n## Other\n\nTranslated text.\n")

    diagnostics = GeneratedOutputEngine().run(QueryHost(snapshot))

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.code == "GEN001"
    assert diagnostic.message == "generated output is missing preserved source anchor"
    assert diagnostic.detail == (
        "source anchor 'jax_at_workaround' from source/lecture.md is absent in "
        "translated/lecture.md"
    )
    assert diagnostic.rule == "generated.preserved_anchor"
    assert diagnostic.span is not None
    assert diagnostic.span.path == PurePosixPath("source/lecture.md")
    assert (diagnostic.span.line, diagnostic.span.col) == (1, 2)


def test_generated_output_engine_is_quiet_when_generated_output_preserves_anchor():
    snapshot = snapshot_for_translation(
        "(jax_at_workaround)=\n## A Workaround\n\n## Other\n\nTranslated text.\n"
    )

    diagnostics = GeneratedOutputEngine().run(QueryHost(snapshot))

    assert diagnostics == ()


def test_generated_profile_keeps_ordinary_reference_checks() -> None:
    document = doc(
        "generated.md",
        "# Generated\n\nSee {ref}`missing-target`.\n",
    )

    result = check_documents(
        (document,),
        config=Config(profile=ProfileConfig(name="generated-myst")),
    )
    default_result = check_documents((document,), config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF004"]
    assert result.diagnostics == default_result.diagnostics


def test_generated_profile_respects_reference_check_toggle() -> None:
    from scieqlint.config.model import ChecksConfig, Config, ProfileConfig, ReferencesConfig

    reference_document = doc(
        "generated.md",
        "# Generated\n\nSee {ref}`missing-target`.\n",
    )
    disabled_references = check_documents(
        (reference_document,),
        config=Config(
            profile=ProfileConfig(name="generated-myst"),
            checks=ChecksConfig(references=ReferencesConfig(enabled=False)),
        ),
    )
    assert disabled_references.diagnostics == ()


def test_generated_profile_reports_only_caller_supplied_dropped_anchor() -> None:
    source = doc(
        "source/lecture.md",
        "(energy)=\n## Energy\n\nText.\n",
    )
    generated = SourceDocument.from_text(
        PurePosixPath("translated/lecture.md"),
        "## Energy\n\nTranslated text.\n",
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(
            source_document_id=source.path.as_posix(),
            tool="translation",
            preserved_anchor_inventory=("energy",),
        ),
    )

    generated_result = check_documents(
        (source, generated),
        config=Config(profile=ProfileConfig(name="generated-myst")),
    )
    default_result = check_documents((source, generated), config=Config())

    assert [
        (diagnostic.code, diagnostic.detail) for diagnostic in generated_result.diagnostics
    ] == [
        (
            "GEN001",
            "source anchor 'energy' from source/lecture.md is absent in translated/lecture.md",
        )
    ]
    assert default_result.diagnostics == ()


def test_documented_generated_workflow_runs_preset_checks_through_paths(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.generated-myst.toml"
    config_path.write_text(read_preset_text("generated-myst"), encoding="utf-8")
    config = load_config(config_path)
    generated = tmp_path / "generated.md"
    generated.write_text("Inline generated math can drift: $\\sin(x) = x$.\n", encoding="utf-8")

    result = check_paths((generated,), config_path=config_path)
    default_result = check_paths((generated,))

    assert config.scanner.inline_math is True
    assert config.parser.strict_unknowns is True
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["PARSE021"]
    assert default_result.diagnostics == ()
