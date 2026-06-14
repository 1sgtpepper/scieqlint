from pathlib import Path, PurePosixPath

from scieqlint.diag.model import SourceSpan
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.facts.reference import GenericRefFact, TargetAnchorFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost

GOOD_FIXTURE = Path("tests/fixtures/good/architecture_myst_good.md")
BAD_FIXTURE = Path("tests/fixtures/bad/architecture_myst_bad.md")


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath("lecture.md"), text, DocumentKind.MARKDOWN)


def fixture_doc(path: Path) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath(path.as_posix()),
        path.read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
    )


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


def test_myst_reference_fixture_extracts_titled_refs_and_equation_roles():
    snapshot = MySTFrontend().lower((fixture_doc(GOOD_FIXTURE),))

    assert [(ref.role_kind, ref.title, ref.target, ref.raw) for ref in snapshot.generic_refs] == [
        (
            "ref",
            "workaround section",
            "qe-workaround",
            "{ref}`workaround section <qe-workaround>`",
        )
    ]
    assert [(ref.ref_kind, ref.target, ref.raw) for ref in snapshot.equation_refs] == [
        ("eq", "eq-bellman", "{eq}`eq-bellman`"),
        ("numref", "eq-bellman", "{numref}`Equation %s <eq-bellman>`"),
    ]
    assert QueryHost(snapshot).references.unresolved_generic_refs() == ()


def test_myst_reference_fixture_reports_orphaned_and_missing_targets():
    snapshot = MySTFrontend().lower((fixture_doc(BAD_FIXTURE),))
    diagnostics = ReferenceEngine().run(QueryHost(snapshot))

    assert [diagnostic.code for diagnostic in diagnostics] == ["REF011", "REF013"]
    assert diagnostics[0].span is not None
    assert diagnostics[0].span.col == 11
    assert diagnostics[1].span is not None
    assert diagnostics[1].span.line == 5


def test_reference_engine_reports_equation_duplicates_and_missing_refs():
    snapshot = MySTFrontend().lower(
        (
            doc(
                "```{math}\n:label: eq-bellman\n\nV = V\n```\n\n"
                "```{math}\n:label: eq-bellman\n\nW = W\n```\n\n"
                "See {eq}`eq-bellman` and {eq}`missing-equation`.\n",
            ),
        )
    )

    diagnostics = ReferenceEngine().run(QueryHost(snapshot))

    assert [diagnostic.code for diagnostic in diagnostics] == [
        "REF001",
        "REF002",
        "REF002",
    ]
    assert diagnostics[0].message == "duplicate equation label: eq-bellman"
    assert diagnostics[1].message == "missing equation reference target: missing-equation"
    assert diagnostics[2].message == "ambiguous equation reference target: eq-bellman"


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
