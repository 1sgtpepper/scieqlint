from pathlib import PurePosixPath

from scieqlint.engine.reference import ReferenceEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath("lecture.md"), text, DocumentKind.MARKDOWN)


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
