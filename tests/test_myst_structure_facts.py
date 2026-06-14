from pathlib import Path, PurePosixPath

from scieqlint.engine.structure import StructureEngine
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


def test_malformed_heading_is_fact_then_engine_diagnostic():
    snapshot = MySTFrontend().lower((doc("####Title\n\n```python\nprint(1)\n```\n"),))
    assert len(snapshot.headings) == 1
    assert snapshot.headings[0].valid_atx is False
    diagnostics = StructureEngine().run(QueryHost(snapshot))
    assert [d.code for d in diagnostics if d.code == "STR001"] == ["STR001"]


def test_heading_inside_code_fence_is_not_lowered():
    snapshot = MySTFrontend().lower((doc("```\n####Not a heading\n```\n"),))
    assert snapshot.headings == ()


def test_valid_myst_structure_fixture_has_attached_anchor_and_no_diagnostics():
    snapshot = MySTFrontend().lower((fixture_doc(GOOD_FIXTURE),))
    diagnostics = StructureEngine().run(QueryHost(snapshot))

    assert [(heading.level, heading.text, heading.valid_atx) for heading in snapshot.headings] == [
        (1, "QuantEcon lecture", True),
        (2, "A Workaround", True),
    ]
    assert [(anchor.label, anchor.placement) for anchor in snapshot.target_anchors] == [
        ("qe-workaround", "before_heading")
    ]
    assert [(fence.kind, fence.info_string, fence.is_closed) for fence in snapshot.fences] == [
        ("math", "{math}", True),
        ("generic", "python", True),
    ]
    assert diagnostics == ()


def test_invalid_myst_structure_fixture_reports_heading_and_fence_diagnostics():
    snapshot = MySTFrontend().lower((fixture_doc(BAD_FIXTURE),))
    diagnostics = StructureEngine().run(QueryHost(snapshot))

    assert [(heading.text, heading.valid_atx) for heading in snapshot.headings] == [
        ("Bad heading", False)
    ]
    assert [(fence.kind, fence.info_string, fence.is_closed) for fence in snapshot.fences] == [
        ("math", "{math}", False)
    ]
    assert [diagnostic.code for diagnostic in diagnostics] == ["STR001", "STR002"]
