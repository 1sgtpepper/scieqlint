from pathlib import PurePosixPath

from scieqlint.diag.model import SourceSpan
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.facts.reference import GenericRefFact, TargetAnchorFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath("lecture.md"), text, DocumentKind.MARKDOWN)


def span(col: int) -> SourceSpan:
    return SourceSpan(
        path=PurePosixPath("lecture.md"),
        start=col - 1,
        end=col,
        line=1,
        col=col,
        end_line=1,
        end_col=col,
    )


def test_anchor_and_ref_resolve():
    snapshot = MySTFrontend().lower(
        (doc("(jax_at_workaround)=\n#### A Workaround\n\nSee {ref}`jax_at_workaround`.\n"),)
    )
    query = QueryHost(snapshot)
    assert snapshot.target_anchors[0].placement == "before_heading"
    assert query.references.unresolved_generic_refs() == ()


def test_missing_ref_reports_target_span():
    snapshot = MySTFrontend().lower((doc("See {ref}`missing`.\n"),))
    diagnostics = ReferenceEngine().run(QueryHost(snapshot))
    assert diagnostics[0].code == "REF011"
    assert diagnostics[0].span is not None
    assert diagnostics[0].span.col == 11


def test_reference_engine_reports_duplicate_ambiguous_and_orphaned_targets():
    first_anchor = TargetAnchorFact(
        fact_id="target-1",
        document_id="lecture.md",
        span=span(1),
        raw="(intro)=",
        label="intro",
        normalized_label="intro",
        target_kind="heading",
        attaches_to_fact_id="heading-1",
        placement="before_heading",
    )
    duplicate_anchor = TargetAnchorFact(
        fact_id="target-2",
        document_id="lecture.md",
        span=span(5),
        raw="(Intro)=",
        label="Intro",
        normalized_label="intro",
        target_kind="heading",
        attaches_to_fact_id="heading-2",
        placement="before_heading",
        label_span=span(6),
    )
    orphaned_anchor = TargetAnchorFact(
        fact_id="target-orphaned",
        document_id="lecture.md",
        span=span(9),
        raw="(loose)=",
        label="loose",
        normalized_label="loose",
        target_kind=None,
        attaches_to_fact_id=None,
        placement="orphaned",
        label_span=span(10),
    )
    ref = GenericRefFact(
        fact_id="ref-1",
        document_id="lecture.md",
        span=span(13),
        raw="{ref}`intro`",
        role_kind="ref",
        target="intro",
        normalized_target="intro",
        target_span=span(19),
    )
    snapshot = FactSnapshot(
        target_anchors=(first_anchor, duplicate_anchor, orphaned_anchor),
        generic_refs=(ref,),
    )

    diagnostics = ReferenceEngine().run(QueryHost(snapshot))

    assert [diagnostic.code for diagnostic in diagnostics] == ["REF010", "REF012", "REF013"]
    assert [diagnostic.span for diagnostic in diagnostics] == [
        duplicate_anchor.label_span,
        ref.target_span,
        orphaned_anchor.label_span,
    ]
