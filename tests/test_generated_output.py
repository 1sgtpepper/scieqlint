from __future__ import annotations

from dataclasses import replace
from pathlib import PurePosixPath

from scieqlint.engine.generated import GeneratedOutputEngine
from scieqlint.facts.generated import GeneratedProvenanceFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
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
