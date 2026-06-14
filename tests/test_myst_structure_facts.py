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


def test_frontend_lowers_myst_cell_reference_and_math_facts():
    snapshot = MySTFrontend().lower(
        (
            doc(
                "\n".join(
                    [
                        "(intro)=",
                        "<!-- translator note -->",
                        "## Introduction",
                        "",
                        "```{code-cell} python",
                        ":label: cell-demo",
                        ":tags: hide-input, remove-output",
                        "print(1)",
                        "```",
                        "",
                        "```python",
                        "#| label: fig-demo",
                        "plot()",
                        "```",
                        "",
                        "```{note}",
                        ":class: tip",
                        "Keep the anchor.",
                        "```",
                        "",
                        "$$",
                        "E = mc^2 \\label{eq-energy}",
                        "$$ {#eq-tail}",
                        "",
                        "```{math}",
                        ":label: eq-directive",
                        "a=b",
                        "```",
                        "",
                        "See [intro](#intro), {ref}`Intro <intro>`, "
                        "{eq}`eq-energy`, and {numref}`eq-tail`.",
                        "Inline $x+1$ is math, but `code $not-math$` is not.",
                    ]
                )
            ),
        )
    )

    assert [(cell.language, cell.label, cell.tags) for cell in snapshot.code_cells] == [
        ("python", "cell-demo", ("hide-input", "remove-output")),
        ("python", "fig-demo", ()),
    ]
    assert [
        (directive.name, directive.argument, directive.option_dict())
        for directive in snapshot.directives
    ] == [
        ("code-cell", "python", {"label": "cell-demo", "tags": "hide-input, remove-output"}),
        ("note", None, {"class": "tip"}),
        ("math", None, {"label": "eq-directive"}),
    ]
    assert [
        (anchor.label, anchor.placement, anchor.target_kind) for anchor in snapshot.target_anchors
    ] == [
        ("intro", "before_heading", "heading")
    ]
    assert [(ref.role_kind, ref.target, ref.title) for ref in snapshot.generic_refs] == [
        ("markdown-link", "intro", None),
        ("ref", "intro", "Intro"),
    ]
    assert [(ref.ref_kind, ref.target) for ref in snapshot.equation_refs] == [
        ("eq", "eq-energy"),
        ("numref", "eq-tail"),
    ]
    assert [(label.label, label.label_syntax_kind) for label in snapshot.equation_labels] == [
        ("eq-directive", "myst-directive-option"),
        ("eq-energy", "tex-label"),
        ("eq-tail", "dollar-tail"),
    ]
    assert [(math.container, math.label_fact_ids) for math in snapshot.display_math] == [
        ("myst-math-directive", (snapshot.equation_labels[0].fact_id,)),
        (
            "dollar-dollar",
            (snapshot.equation_labels[1].fact_id, snapshot.equation_labels[2].fact_id),
        ),
    ]
    assert [math.body for math in snapshot.inline_math] == ["x+1"]
