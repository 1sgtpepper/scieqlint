from __future__ import annotations

from dataclasses import replace
from pathlib import PurePosixPath

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


def test_generated_profile_uses_one_fact_snapshot_for_reference_structure_and_generated_engines(
    monkeypatch,
):
    document = doc(
        "generated.md",
        "# Generated\n\nSee {ref}`missing-target`.\n",
    )
    calls = 0
    original_lower = MySTFrontend.lower

    def count_lower(self, documents):
        nonlocal calls
        calls += 1
        return original_lower(self, documents)

    monkeypatch.setattr(MySTFrontend, "lower", count_lower)

    from scieqlint.app import check_documents
    from scieqlint.config.model import Config, ProfileConfig

    result = check_documents(
        (document,),
        config=Config(profile=ProfileConfig(name="generated-myst")),
    )

    assert calls == 1
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF004"]


def test_generated_profile_gates_reference_and_profile_paths() -> None:
    from scieqlint.app import check_documents
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
    default_profile = check_documents((doc("generated.md", "# Generated\n"),), config=Config())

    assert disabled_references.diagnostics == ()
    assert default_profile.diagnostics == ()


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

    assert [(diagnostic.code, diagnostic.detail) for diagnostic in generated_result.diagnostics] == [
        (
            "GEN001",
            "source anchor 'energy' from source/lecture.md is absent in "
            "translated/lecture.md",
        )
    ]
    assert default_result.diagnostics == ()
