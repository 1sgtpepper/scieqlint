from pathlib import PurePosixPath

from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost
from scieqlint.engine.structure import StructureEngine


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath("lecture.md"), text, DocumentKind.MARKDOWN)


def test_malformed_heading_is_fact_then_engine_diagnostic():
    snapshot = MySTFrontend().lower((doc("####Title\n\n```python\nprint(1)\n```\n"),))
    assert len(snapshot.headings) == 1
    assert snapshot.headings[0].valid_atx is False
    diagnostics = StructureEngine().run(QueryHost(snapshot))
    assert [d.code for d in diagnostics if d.code == "STR001"] == ["STR001"]


def test_heading_inside_code_fence_is_not_lowered():
    snapshot = MySTFrontend().lower((doc("```\n####Not a heading\n```\n"),))
    assert snapshot.headings == ()
