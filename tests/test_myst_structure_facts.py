from dataclasses import replace
from pathlib import Path, PurePosixPath

from scieqlint.engine.reference import ReferenceEngine
from scieqlint.engine.structure import StructureEngine
from scieqlint.frontend.myst import (
    MySTFrontend,
    _is_immediate_attachment,
    _myst_options,
    _quarto_options,
)
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
    query = QueryHost(snapshot)
    diagnostics = (*StructureEngine().run(query), *ReferenceEngine().run(query))

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


def test_myst_heading_anchors_resolve_markdownlint_sensitive_links():
    snapshot = MySTFrontend().lower(
        (
            doc(
                "\n".join(
                    [
                        "(intro)=",
                        "# Introduction",
                        "",
                        "(empty-link-target)=",
                        "## Empty link target",
                        "",
                        "See [](#intro), [#empty-link-target](#empty-link-target), "
                        "and {ref}`Introduction <intro>`.",
                    ]
                )
            ),
        )
    )
    query = QueryHost(snapshot)
    diagnostics = (*StructureEngine().run(query), *ReferenceEngine().run(query))

    assert [(heading.text, heading.valid_atx) for heading in snapshot.headings] == [
        ("Introduction", True),
        ("Empty link target", True),
    ]
    assert [(anchor.label, anchor.placement) for anchor in snapshot.target_anchors] == [
        ("intro", "before_heading"),
        ("empty-link-target", "before_heading"),
    ]
    assert [(ref.role_kind, ref.target) for ref in snapshot.generic_refs] == [
        ("markdown-link", "intro"),
        ("markdown-link", "empty-link-target"),
        ("ref", "intro"),
    ]
    assert diagnostics == ()


def test_missing_and_orphaned_generic_refs_are_diagnosed():
    snapshot = MySTFrontend().lower(
        (
            doc(
                "\n".join(
                    [
                        "See {ref}`missing-target`.",
                        "",
                        "(loose-anchor)=",
                        "This paragraph leaves the anchor unattached.",
                        "",
                        "See {ref}`loose-anchor`.",
                    ]
                )
            ),
        )
    )
    diagnostics = ReferenceEngine().run(QueryHost(snapshot))

    assert [(anchor.label, anchor.placement) for anchor in snapshot.target_anchors] == [
        ("loose-anchor", "orphaned")
    ]
    assert [(diagnostic.code, diagnostic.detail) for diagnostic in diagnostics] == [
        ("REF004", "reference text: {ref}`missing-target`"),
        ("REF004", "reference text: {ref}`loose-anchor`"),
    ]


def test_duplicate_generic_targets_are_diagnosed_distinctly_from_missing_targets():
    snapshot = MySTFrontend().lower(
        (
            doc(
                "\n".join(
                    [
                        "(intro)=",
                        "# Introduction",
                        "",
                        "(intro)=",
                        "## Duplicate Introduction",
                        "",
                        "See {ref}`intro`.",
                    ]
                )
            ),
        )
    )
    diagnostics = ReferenceEngine().run(QueryHost(snapshot))

    assert [(anchor.label, anchor.placement) for anchor in snapshot.target_anchors] == [
        ("intro", "before_heading"),
        ("intro", "before_heading"),
    ]
    assert [(diagnostic.code, diagnostic.detail) for diagnostic in diagnostics] == [
        ("REF005", "reference text: {ref}`intro`")
    ]


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
                        ":name: eq-directive-name",
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
        ("math", None, {"name": "eq-directive-name", "label": "eq-directive"}),
    ]
    assert [
        (anchor.label, anchor.placement, anchor.target_kind) for anchor in snapshot.target_anchors
    ] == [("intro", "before_heading", "heading")]
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


def test_frontend_helpers_ignore_spanless_or_bodyless_synthetic_facts():
    source = doc(
        "\n".join(
            [
                "(intro)=",
                "# Intro",
                "",
                "```{note}",
                ":class: tip",
                "```",
                "",
                "```python",
                "#| label: fig-demo",
                "```",
            ]
        )
    )
    snapshot = MySTFrontend().lower((source,))

    assert _myst_options(source, replace(snapshot.fences[0], body_span=None)) == ()
    assert _quarto_options(source, replace(snapshot.fences[1], body_span=None)) == ()
    assert (
        _is_immediate_attachment(
            source,
            replace(snapshot.target_anchors[0], span=None),
            snapshot.headings[0],
        )
        is False
    )


def test_frontend_distinguishes_occupied_markup_and_sparse_cells():
    snapshot = MySTFrontend().lower(
        (
            doc(
                "\n".join(
                    [
                        "###   ",
                        "# Part One",
                        "## Child",
                        "# Part Two",
                        "",
                        "```",
                        "[hidden](#inside) {ref}`inside` $$hidden$$",
                        "```",
                        "",
                        "```python",
                        "```",
                        "",
                        "```{note}",
                        "```",
                        "",
                        "```{code-cell}",
                        "print(1)",
                        "```",
                        "",
                        "{ref}`Part One <#part-one>`",
                        "$$",
                        "no close",
                    ]
                )
            ),
            doc(
                "\n".join(
                    [
                        "$$",
                        "visible",
                        "```",
                        "$$",
                        "```",
                        "$$ {#eq-end}",
                    ]
                )
            ),
        )
    )
    diagnostics = StructureEngine().run(QueryHost(snapshot))

    assert [(heading.level, heading.text) for heading in snapshot.headings] == [
        (1, "Part One"),
        (2, "Child"),
        (1, "Part Two"),
    ]
    assert [(section.depth, section.parent_section_id) for section in snapshot.sections] == [
        (1, None),
        (2, snapshot.sections[0].fact_id),
        (1, None),
    ]
    assert [(cell.language, cell.label) for cell in snapshot.code_cells] == [
        ("python", None),
        (None, None),
    ]
    assert [(directive.name, directive.options) for directive in snapshot.directives] == [
        ("note", ()),
        ("code-cell", ()),
    ]
    assert [(ref.target, ref.normalized_target) for ref in snapshot.generic_refs] == [
        ("#part-one", "part-one")
    ]
    assert [(label.label, label.label_syntax_kind) for label in snapshot.equation_labels] == [
        ("eq-end", "dollar-tail")
    ]
    assert [math.body for math in snapshot.display_math] == ["visible\n```\n$$\n```"]
    assert [diagnostic.code for diagnostic in diagnostics] == ["STR003", "STR003", "DIR010"]
