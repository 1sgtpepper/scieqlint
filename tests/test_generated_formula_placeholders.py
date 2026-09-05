from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest

from scieqlint.api import check_documents
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.parse.math import MathHost
from scieqlint.report.json import JsonReporter
from scieqlint.source.maps import SourceMap


def doc(text: str, *, origin: SourceOrigin | None = None) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("generated.md"),
        text,
        DocumentKind.MARKDOWN,
        origin=origin,
    )


def placeholder_facts(text: str):
    return tuple(
        fact
        for fact in MathHost().classify(MySTFrontend().lower((doc(text),))).generated_formulas
        if fact.placeholder_kind is not None
    )


def generated_result(text: str):
    return check_documents(
        (
            doc(
                text,
                origin=SourceOrigin(
                    source_document_id="source/formulas.xml",
                    source_kind="jats-xml",
                    conversion_stage="xml-to-markdown",
                ),
            ),
        ),
        config=Config(profile=ProfileConfig(name="generated-myst")),
    )


def assert_public_gen004_contract(
    result,
    source: str,
    expected: tuple[tuple[str, str, str, int, int, int, int, int], ...],
) -> None:
    assert [item.code for item in result.diagnostics] == ["GEN004"] * len(expected)
    diagnostics = result.diagnostics

    assert len(diagnostics) == len(expected)
    assert [item.severity.value for item in diagnostics] == ["warning"] * len(expected)
    assert [item.rule for item in diagnostics] == ["generated.formula_placeholder"] * len(expected)
    assert [item.profile for item in diagnostics] == ["generated-myst"] * len(expected)
    assert [item.provenance_ids for item in diagnostics] == [
        ("generated.md::generated-provenance",)
    ] * len(expected)

    expected_properties = [
        {
            "formula_artifact_kind": artifact_kind,
            "placeholder_kind": placeholder_kind,
            "generated_document": "generated.md",
            "source_document": "source/formulas.xml",
            "source_kind": "jats-xml",
            "conversion_stage": "xml-to-markdown",
        }
        for artifact_kind, placeholder_kind, *_ in expected
    ]
    assert [dict(item.properties) for item in diagnostics] == expected_properties

    expected_spans = []
    for (
        _artifact_kind,
        _placeholder_kind,
        span_text,
        occurrence,
        line,
        col,
        end_line,
        end_col,
    ) in expected:
        start = -1
        for _ in range(occurrence + 1):
            start = source.index(span_text, start + 1)
        expected_spans.append(
            (
                PurePosixPath("generated.md"),
                start,
                start + len(span_text),
                line,
                col,
                end_line,
                end_col,
                span_text,
            )
        )

    assert [
        (
            item.span.path,
            item.span.start,
            item.span.end,
            item.span.line,
            item.span.col,
            item.span.end_line,
            item.span.end_col,
            source[item.span.start : item.span.end],
        )
        for item in diagnostics
        if item.span is not None
    ] == expected_spans


def test_formula_placeholder_facts_cover_marker_empty_display_and_formula_image() -> None:
    fence = chr(96) * 3
    source = f"""\
<!-- formula-not-decoded -->

$formula-not-decoded$

$$   $$

$$$$

{fence}math
{fence}

![formula](assets/equation-placeholder.svg)
"""

    facts = placeholder_facts(source)

    assert [fact.kind for fact in facts] == [
        "placeholder",
        "placeholder",
        "empty-display",
        "empty-display",
        "empty-display",
        "image-placeholder",
    ]
    assert [fact.placeholder_kind for fact in facts] == [
        "formula-not-decoded",
        "formula-not-decoded",
        "empty-display-math",
        "empty-display-math",
        "empty-display-math",
        "formula-image",
    ]
    assert [source[fact.span.start : fact.span.end] for fact in facts if fact.span is not None] == [
        "<!-- formula-not-decoded -->",
        "formula-not-decoded",
        "$$   $$",
        "$$$$",
        "",
        "![formula](assets/equation-placeholder.svg)",
    ]


@pytest.mark.parametrize(
    ("source", "expected_kind", "expected_span"),
    [
        ("- formula-not-decoded\n", "formula-not-decoded", "formula-not-decoded"),
        (
            "- <!-- formula-not-decoded -->\n",
            "formula-not-decoded",
            "<!-- formula-not-decoded -->",
        ),
        ("- $$$$\n", "empty-display-math", "$$$$"),
        (
            "- ![formula](assets/equation-placeholder.svg)\n",
            "formula-image",
            "![formula](assets/equation-placeholder.svg)",
        ),
        ("> formula-not-decoded\n", "formula-not-decoded", "formula-not-decoded"),
        (
            "> <!-- formula-not-decoded -->\n",
            "formula-not-decoded",
            "<!-- formula-not-decoded -->",
        ),
        ("> $$$$\n", "empty-display-math", "$$$$"),
        (
            "> ![formula](assets/equation-placeholder.svg)\n",
            "formula-image",
            "![formula](assets/equation-placeholder.svg)",
        ),
        (
            "- outer\n\t- <!-- formula-not-decoded -->\n",
            "formula-not-decoded",
            "<!-- formula-not-decoded -->",
        ),
        (
            "- outer\n\t- ![formula](assets/equation-placeholder.svg)\n",
            "formula-image",
            "![formula](assets/equation-placeholder.svg)",
        ),
    ],
    ids=(
        "list-marker",
        "list-comment-marker",
        "list-empty-display",
        "list-formula-image",
        "blockquote-marker",
        "blockquote-comment-marker",
        "blockquote-empty-display",
        "blockquote-formula-image",
        "tab-nested-list-comment-marker",
        "tab-nested-list-formula-image",
    ),
)
def test_formula_placeholders_use_container_relative_content_and_raw_spans(
    source: str,
    expected_kind: str,
    expected_span: str,
) -> None:
    facts = placeholder_facts(source)

    assert len(facts) == 1
    [fact] = facts
    assert fact.span is not None
    assert (fact.placeholder_kind, source[fact.span.start : fact.span.end]) == (
        expected_kind,
        expected_span,
    )


def test_adjacent_source_owned_comment_markers_remain_separate_candidates() -> None:
    source = "- <!-- formula-not-decoded -->\n- <!-- formula-not-decoded -->\n"

    facts = placeholder_facts(source)

    assert [source[fact.span.start : fact.span.end] for fact in facts if fact.span is not None] == [
        "<!-- formula-not-decoded -->",
        "<!-- formula-not-decoded -->",
    ]


@pytest.mark.parametrize(
    "source",
    [
        "- formula-not-decoded\n  continued prose\n",
        "> formula-not-decoded\n> continued prose\n",
        "- $$$$\n  continued prose\n",
        "> $$$$\n> continued prose\n",
        "- ![formula](assets/equation-placeholder.svg)\n  continued prose\n",
        "> ![formula](assets/equation-placeholder.svg)\n> continued prose\n",
    ],
    ids=(
        "list-marker-continuation",
        "blockquote-marker-continuation",
        "list-empty-display-continuation",
        "blockquote-empty-display-continuation",
        "list-image-continuation",
        "blockquote-image-continuation",
    ),
)
def test_formula_placeholders_reject_container_continued_prose(source: str) -> None:
    assert placeholder_facts(source) == ()


def test_empty_fenced_math_is_a_placeholder_but_content_is_not() -> None:
    fence = chr(96) * 3
    empty_source = f"Before.\n{fence}math\n{fence}\nAfter.\n"

    facts = placeholder_facts(empty_source)

    assert [(fact.kind, fact.placeholder_kind) for fact in facts] == [
        ("empty-display", "empty-display-math")
    ]
    [fact] = facts
    assert fact.span is not None
    expected_body_start = empty_source.index(f"{fence}math\n") + len(f"{fence}math\n")
    assert (fact.span.start, fact.span.end) == (expected_body_start, expected_body_start)

    content_source = f"Before.\n{fence}math\nx = 1\n{fence}\nAfter.\n"
    assert placeholder_facts(content_source) == ()


def test_unclosed_empty_fenced_math_is_not_a_complete_placeholder() -> None:
    fence = chr(96) * 3

    assert placeholder_facts(f"Before.\n{fence}math\n") == ()


@pytest.mark.parametrize(
    "body",
    [
        ":label: generated-equation\n",
        "% formula was omitted by the converter\n",
        ":label: generated-equation\n% formula was omitted by the converter\n",
    ],
    ids=("option-only", "comment-only", "option-and-comment"),
)
def test_empty_myst_math_directive_ignores_options_and_tex_comments(body: str) -> None:
    source = f"```{{math}}\n{body}```\n\n```{{math}}\nx = 1\n```\n"

    facts = placeholder_facts(source)

    assert [(fact.kind, fact.placeholder_kind) for fact in facts] == [
        ("empty-display", "empty-display-math")
    ]
    [fact] = facts
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == body


@pytest.mark.parametrize(
    "options",
    [
        ":label: eq-missing\n",
        ":name: missing\n\n",
        ":alt: formula-not-decoded\n",
        ":label: eq-missing\n% converter comment\n",
    ],
)
def test_formula_markers_ignore_directive_options_with_exact_body_spans(options: str) -> None:
    marker = "formula-not-decoded"
    source = (
        f"```{{math}}\n{options}{marker} % omitted formula\n```\n\n"
        "```{math}\n:alt: formula-not-decoded\nx = 1\n```\n"
    )

    facts = placeholder_facts(source)
    assert len(facts) == 1
    [fact] = facts
    assert (fact.kind, fact.placeholder_kind) == ("placeholder", marker)
    assert fact.span is not None
    expected_start = len("```{math}\n") + len(options)
    assert (fact.span.start, fact.span.end) == (expected_start, expected_start + len(marker))
    assert source[fact.span.start : fact.span.end] == marker
    result = generated_result(source)
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["GEN004"]
    assert result.diagnostics[0].span == fact.span


def test_nonempty_myst_math_directive_is_not_mistaken_for_an_empty_placeholder() -> None:
    source = "```{math}\n:label: generated-equation\nx = 1\n```\n"

    assert placeholder_facts(source) == ()


@pytest.mark.public_regression
def test_public_api_reports_empty_myst_math_directive_and_keeps_content_active() -> None:
    fence = chr(96) * 3
    source = (
        f"{fence}{{math}}\n"
        ":label: generated-equation\n"
        "% formula was omitted by the converter\n"
        f"{fence}\n\n"
        f"{fence}{{math}}\n"
        "x = 1\n"
        f"{fence}\n"
    )

    assert_public_gen004_contract(
        generated_result(source),
        source,
        (
            (
                "empty-display",
                "empty-display-math",
                ":label: generated-equation\n% formula was omitted by the converter\n",
                0,
                2,
                1,
                3,
                39,
            ),
        ),
    )


@pytest.mark.parametrize(
    "heading_text",
    [
        "formula-not-decoded",
        "$$$$",
        "![formula placeholder](equation.svg)",
    ],
    ids=("marker", "empty-display", "formula-image"),
)
def test_setext_heading_text_is_not_a_formula_placeholder(heading_text: str) -> None:
    source = f"{heading_text}\n---\n\nformula-not-decoded\n"

    facts = placeholder_facts(source)

    assert len(facts) == 1
    [fact] = facts
    assert fact.placeholder_kind == "formula-not-decoded"
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == "formula-not-decoded"
    assert fact.span.start == source.rfind("formula-not-decoded")


@pytest.mark.public_regression
def test_public_api_ignores_setext_heading_and_reports_active_marker() -> None:
    source = "formula-not-decoded\n---\n\nformula-not-decoded\n\n![equation](equation.svg)\n"

    assert_public_gen004_contract(
        generated_result(source),
        source,
        (("placeholder", "formula-not-decoded", "formula-not-decoded", 1, 4, 1, 4, 19),),
    )


@pytest.mark.parametrize(
    ("prefix", "candidate", "expected_kind", "expected_span"),
    [
        ("# Heading\n", "formula-not-decoded", "formula-not-decoded", "formula-not-decoded"),
        ("# Heading\n", "$$$$", "empty-display-math", "$$$$"),
        (
            "# Heading\n",
            "![formula placeholder](equation.svg)",
            "formula-image",
            "![formula placeholder](equation.svg)",
        ),
        (
            "```math\nx = 1\n```\n",
            "formula-not-decoded",
            "formula-not-decoded",
            "formula-not-decoded",
        ),
        ("$$\nx = 1\n$$\n", "formula-not-decoded", "formula-not-decoded", "formula-not-decoded"),
        (
            "<!-- completed HTML block -->\n",
            "formula-not-decoded",
            "formula-not-decoded",
            "formula-not-decoded",
        ),
    ],
    ids=(
        "heading-marker",
        "heading-empty-display",
        "heading-formula-image",
        "fenced-math-marker",
        "dollar-display-marker",
        "html-comment-marker",
    ),
)
def test_placeholder_after_completed_block_starts_a_new_text_item(
    prefix: str,
    candidate: str,
    expected_kind: str,
    expected_span: str,
) -> None:
    source = f"{prefix}{candidate}\n"

    facts = placeholder_facts(source)

    assert len(facts) == 1
    [fact] = facts
    assert fact.placeholder_kind == expected_kind
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == expected_span


def test_list_lazy_continuation_remains_prose_after_a_list_item_start() -> None:
    source = "- ordinary prose\n  formula-not-decoded\n"

    assert placeholder_facts(source) == ()


@pytest.mark.public_regression
def test_public_api_reports_markers_after_completed_blocks_but_not_continuation() -> None:
    fence = chr(96) * 3
    source = (
        "ordinary prose\n"
        "formula-not-decoded\n\n"
        "# Heading\n"
        "formula-not-decoded\n\n"
        f"{fence}math\n"
        "x = 1\n"
        f"{fence}\n"
        "formula-not-decoded\n\n"
        "<!-- completed HTML block -->\n"
        "formula-not-decoded\n"
    )

    assert_public_gen004_contract(
        generated_result(source),
        source,
        (
            ("placeholder", "formula-not-decoded", "formula-not-decoded", 1, 5, 1, 5, 19),
            ("placeholder", "formula-not-decoded", "formula-not-decoded", 2, 10, 1, 10, 19),
            ("placeholder", "formula-not-decoded", "formula-not-decoded", 3, 13, 1, 13, 19),
        ),
    )


@pytest.mark.parametrize(
    "source",
    [
        "> - <!-- formula-not-decoded -->\n",
        "> > <!-- formula-not-decoded -->\n",
        ">  > <!-- formula-not-decoded -->\n",
    ],
    ids=("nested-list", "nested-quote", "spaced-nested-quote"),
)
def test_nested_owned_html_marker_uses_container_content_start(source: str) -> None:
    facts = placeholder_facts(source)

    assert len(facts) == 1
    [fact] = facts
    assert fact.placeholder_kind == "formula-not-decoded"
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == "<!-- formula-not-decoded -->"


def test_nested_html_block_content_remains_opaque() -> None:
    source = "> - <div>\n>   formula-not-decoded\n> </div>\n"

    assert placeholder_facts(source) == ()


@pytest.mark.public_regression
def test_public_api_reports_nested_owned_comment_but_not_opaque_html_content() -> None:
    source = "> - <!-- formula-not-decoded -->\n\n> - <div>\n>   formula-not-decoded\n> </div>\n"

    assert_public_gen004_contract(
        generated_result(source),
        source,
        (
            (
                "placeholder",
                "formula-not-decoded",
                "<!-- formula-not-decoded -->",
                0,
                1,
                5,
                1,
                32,
            ),
        ),
    )


def test_empty_raw_equation_is_a_placeholder_but_unsupported_and_incomplete_forms_are_not() -> None:
    source = (
        "\\begin{equation}\n\\end{equation}\n\n"
        "\\begin{cases}\n\\end{cases}\n\n"
        "\\begin{figure}\n\\end{figure}\n\n"
        "\\begin{equation}\n\n"
        "The formula-not-decoded marker is discussed in prose.\n"
    )

    facts = placeholder_facts(source)

    assert len(facts) == 1
    [fact] = facts
    assert fact.placeholder_kind == "empty-display-math"
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == "\\begin{equation}\n\\end{equation}"


def test_raw_formula_marker_placeholder_span_is_limited_to_the_marker_token() -> None:
    source = "\\begin{equation}\n  formula-not-decoded  \n\\end{equation}\n"

    [fact] = placeholder_facts(source)

    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == "formula-not-decoded"


def test_generated_profile_reports_raw_formula_marker_before_an_active_tex_comment() -> None:
    source = "\\begin{equation}\nformula-not-decoded % generated marker\n\\end{equation}\n"
    result = check_documents(
        (doc(source, origin=SourceOrigin(source_document_id="source/formulas.tex")),),
        config=Config(profile=ProfileConfig(name="generated-myst")),
    )

    diagnostics = [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "GEN004"]

    [diagnostic] = diagnostics
    assert diagnostic.span is not None
    assert source[diagnostic.span.start : diagnostic.span.end] == "formula-not-decoded"


def test_generated_profile_filters_unaccepted_raw_formula_markers() -> None:
    source = (
        "\\begin{equation}\nformula-not-decoded\n\\end{equation}\n\n"
        "\\begin{cases}\nformula-not-decoded\n\\end{cases}\n\n"
        "\\begin{equation}\nformula-not-decoded\n"
    )
    result = check_documents(
        (doc(source, origin=SourceOrigin(source_document_id="source/formulas.tex")),),
        config=Config(profile=ProfileConfig(name="generated-myst")),
    )

    diagnostics = [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "GEN004"]

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.span is not None
    assert source[diagnostic.span.start : diagnostic.span.end] == "formula-not-decoded"


def test_many_standalone_markers_preserve_source_ordered_spans() -> None:
    marker = "formula-not-decoded"
    source = "\n\n".join(marker for _ in range(256)) + "\n"

    facts = placeholder_facts(source)

    assert len(facts) == 256
    assert all(fact.placeholder_kind == "formula-not-decoded" for fact in facts)
    assert [(fact.span.start, fact.span.end) for fact in facts if fact.span is not None] == [
        (index * (len(marker) + 2), index * (len(marker) + 2) + len(marker)) for index in range(256)
    ]


def test_formula_marker_ignores_active_but_not_escaped_tex_comments() -> None:
    fence = chr(96) * 3
    source = (
        f"{fence}math\n"
        "formula-not-decoded % generated marker\n"
        f"{fence}\n\n"
        f"{fence}math\n"
        "formula-not-decoded \\% visible content\n"
        f"{fence}\n"
    )

    [fact] = placeholder_facts(source)

    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == "formula-not-decoded"


def test_placeholder_scanner_rejects_prose_code_nonempty_math_and_nonformula_images() -> None:
    source = """\
The formula-not-decoded marker is discussed in prose.

`formula-not-decoded`

```text
formula-not-decoded
$$$$
![formula](formula.png)
```

$$x = 1$$

![plot of an equation](equation-of-state.png)

Text ![formula](formula.png) is not a standalone formula position.
"""

    assert placeholder_facts(source) == ()


def test_empty_display_detection_reuses_math_container_ownership() -> None:
    source = """\
```text
$$   $$
```

<!--
$$   $$
-->

$$   $$
"""

    facts = placeholder_facts(source)

    assert len(facts) == 1
    assert facts[0].span is not None
    assert source[facts[0].span.start : facts[0].span.end] == "$$   $$"


def test_placeholder_scanner_does_not_duplicate_an_empty_dollar_marker() -> None:
    from scieqlint.frontend.generated import scan_formula_placeholders

    document = doc("$$$$\n")

    facts = scan_formula_placeholders(
        document,
        SourceMap.for_document(document),
        (),
        (),
        ((0, 2, 2, 4),),
        (),
        (),
        (),
    )

    assert [(fact.kind, fact.placeholder_kind) for fact in facts] == [
        ("candidate", "empty-display-math")
    ]


@pytest.mark.parametrize(
    "source",
    [
        "<!--\n$$$$\n-->\n",
        "<div>\n$$$$\n</div>\n",
        "    $$$$\n",
        "    <!-- formula-not-decoded -->\n",
        "<div>\n<!-- formula-not-decoded -->\n</div>\n",
        "<!--\n<!-- formula-not-decoded -->\n-->\n",
        "<!--\n\n<!-- formula-not-decoded -->\n\n-->\n",
        "<script>\n\n<!-- formula-not-decoded -->\n\n</script>\n",
    ],
    ids=(
        "html-comment",
        "raw-html",
        "indented-code",
        "indented-marker-comment",
        "raw-html-marker-comment",
        "nested-html-marker-comment",
        "nested-html-marker-comment-after-blank",
        "script-marker-comment-after-blank",
    ),
)
def test_empty_display_marker_respects_opaque_markdown_ownership(source: str) -> None:
    assert placeholder_facts(source) == ()


def test_formula_marker_respects_raw_html_ownership() -> None:
    assert placeholder_facts("<div>\nformula-not-decoded\n</div>\n") == ()


def test_formula_placeholders_respect_existing_display_math_ownership() -> None:
    source = "$$\nx = 1\n\n$$$$\n\n$$\n"

    assert placeholder_facts(source) == ()


def test_unclosed_latex_paren_does_not_hide_later_formula_placeholder() -> None:
    source = "\\(\nx = 1\n\n$$$$\n\ny = 2\n\\)\n"

    facts = placeholder_facts(source)

    assert [(fact.kind, fact.placeholder_kind, fact.text) for fact in facts] == [
        ("empty-display", "empty-display-math", "$$$$")
    ]
    [fact] = facts
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == "$$$$"


def test_placeholder_sweeps_preserve_many_dollar_and_image_candidates() -> None:
    source = "\n\n".join(["$$   $$"] * 64 + ["![equation](formula-placeholder.png)"] * 64) + "\n"

    facts = placeholder_facts(source)

    assert len(facts) == 128
    assert [fact.placeholder_kind for fact in facts].count("empty-display-math") == 64
    assert [fact.placeholder_kind for fact in facts].count("formula-image") == 64
    assert [fact.span.start for fact in facts if fact.span] == sorted(
        fact.span.start for fact in facts if fact.span
    )


class _ComparisonCountingOffset(int):
    comparisons = 0

    def __lt__(self, other: object) -> bool:
        assert isinstance(other, int)
        type(self).comparisons += 1
        return int(self) < int(other)

    def __le__(self, other: object) -> bool:
        assert isinstance(other, int)
        type(self).comparisons += 1
        return int(self) <= int(other)


def test_marker_opaque_ownership_sweep_has_bounded_work() -> None:
    from scieqlint.frontend.generated import scan_formula_placeholders

    marker = "<!-- formula-not-decoded -->"
    count = 128
    source = "\n\n".join(marker for _ in range(count)) + "\n"
    document = doc(source)
    opaque = tuple(
        (
            _ComparisonCountingOffset(start),
            _ComparisonCountingOffset(start + len(marker)),
        )
        for start in range(0, count * (len(marker) + 2), len(marker) + 2)
    )
    _ComparisonCountingOffset.comparisons = 0

    facts = scan_formula_placeholders(
        document,
        SourceMap.for_document(document),
        (),
        (),
        (),
        (),
        opaque,
        (),
    )

    assert [fact.span.start for fact in facts if fact.span is not None] == [
        int(start) for start, _end in opaque
    ]
    # Merging and sweeping may compare each range a small fixed number of times;
    # restarting ownership lookup from the first range exceeds this linear budget.
    assert _ComparisonCountingOffset.comparisons <= len(opaque) * 24


def test_formula_image_placeholder_requires_explicit_placeholder_evidence() -> None:
    facts = placeholder_facts("![equation placeholder](equation.svg)")

    assert [(fact.kind, fact.placeholder_kind, fact.text) for fact in facts] == [
        ("image-placeholder", "formula-image", "![equation placeholder](equation.svg)")
    ]


def test_rendered_equation_image_is_not_a_formula_placeholder() -> None:
    facts = placeholder_facts("![equation](equation.svg)")

    assert facts == ()


def test_formula_image_continuing_prose_is_not_a_generated_diagnostic() -> None:
    source = "![formula](formula-placeholder.svg)\ncontinued prose\n"
    config = Config(profile=ProfileConfig(name="generated-myst"))

    result = check_documents(
        (doc(source, origin=SourceOrigin(source_document_id="source/formulas.xml")),),
        config=config,
    )
    assert [
        diagnostic.code for diagnostic in result.diagnostics if diagnostic.code == "GEN004"
    ] == []

    control = check_documents(
        (
            doc(
                "![formula](formula-placeholder.svg)\n",
                origin=SourceOrigin(source_document_id="source/formulas.xml"),
            ),
        ),
        config=config,
    )
    assert [
        diagnostic.code for diagnostic in control.diagnostics if diagnostic.code == "GEN004"
    ] == ["GEN004"]


@pytest.mark.parametrize(
    ("destination", "expected"),
    [
        ("assets/formula-placeholder.png?source=generated", True),
        ("assets/formula-placeholder.png#crop", True),
        ("assets/equation.svg?source=rendered", False),
    ],
)
def test_formula_image_placeholder_matches_resource_name_without_url_suffix(
    destination: str, expected: bool
) -> None:
    assert bool(placeholder_facts(f"![render]({destination})\n")) is expected


def test_generated_profile_json_matches_placeholder_golden() -> None:
    result = check_documents(
        (
            doc(
                "Before.\n\n![equation](assets/formula-placeholder.png?source=generated)\n",
                origin=SourceOrigin(source_document_id="source/formulas.xml"),
            ),
        ),
        config=Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="jats-xml",
                conversion_stage="xml-to-markdown",
            )
        ),
    )

    assert JsonReporter().render(result) == Path(
        "tests/golden/json/generated_formula_placeholders.json"
    ).read_text(encoding="utf-8")


def test_formula_image_placeholders_use_complete_markdown_link_boundaries() -> None:
    source = (
        "![formula placeholder](assets/equation-(draft-(v2)).svg)\n\n"
        r"![equation placeholder](assets/equation\).svg)" + "\n\n"
        '![formula placeholder](assets/equation.svg "title\ncontinued")\n'
    )

    facts = placeholder_facts(source)

    assert [fact.placeholder_kind for fact in facts] == [
        "formula-image",
        "formula-image",
        "formula-image",
    ]
    assert [source[fact.span.start : fact.span.end] for fact in facts if fact.span is not None] == [
        "![formula placeholder](assets/equation-(draft-(v2)).svg)",
        r"![equation placeholder](assets/equation\).svg)",
        '![formula placeholder](assets/equation.svg "title\ncontinued")',
    ]


@pytest.mark.parametrize(
    "source",
    [
        '- ![formula placeholder](equation.svg "title\ncontinued")\n',
        '> ![formula placeholder](equation.svg "title\ncontinued")\n',
    ],
    ids=("list-multiline-title", "blockquote-multiline-title"),
)
def test_formula_image_placeholders_accept_multiline_titles_inside_one_container(
    source: str,
) -> None:
    facts = placeholder_facts(source)

    assert len(facts) == 1
    [fact] = facts
    assert fact.placeholder_kind == "formula-image"
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == (
        '![formula placeholder](equation.svg "title\ncontinued")'
    )


@pytest.mark.parametrize(
    "source",
    [
        '- ![formula placeholder](equation.svg "title\ncontinued")\n  trailing prose\n',
        '> ![formula placeholder](equation.svg "title\ncontinued")\n> trailing prose\n',
        '- ![formula placeholder](equation.svg "title\n> continued")\n',
        '> ![formula placeholder](equation.svg "title\n- continued")\n',
    ],
    ids=(
        "list-multiline-title-trailing-prose",
        "blockquote-multiline-title-trailing-prose",
        "list-cross-container-title",
        "blockquote-cross-container-title",
    ),
)
def test_formula_image_placeholders_reject_trailing_prose_and_cross_container_titles(
    source: str,
) -> None:
    assert placeholder_facts(source) == ()


def test_generated_profile_json_preserves_span_and_placeholder_kind() -> None:
    source = "Before.\n\n![equation placeholder](equation.svg)\n"
    result = check_documents(
        (
            doc(
                source,
                origin=SourceOrigin(source_document_id="source/formulas.xml"),
            ),
        ),
        config=Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="jats-xml",
                conversion_stage="xml-to-markdown",
            )
        ),
    )
    diagnostics = tuple(
        diagnostic for diagnostic in result.diagnostics if diagnostic.code == "GEN004"
    )

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.span is not None
    assert (diagnostic.span.line, diagnostic.span.col) == (3, 1)
    assert dict(diagnostic.properties) == {
        "formula_artifact_kind": "image-placeholder",
        "placeholder_kind": "formula-image",
        "generated_document": "generated.md",
        "source_document": "source/formulas.xml",
        "source_kind": "jats-xml",
        "conversion_stage": "xml-to-markdown",
    }

    payload = json.loads(JsonReporter().render(result))
    generated = next(item for item in payload["diagnostics"] if item["code"] == "GEN004")
    assert (generated["path"], generated["line"], generated["col"]) == (
        "generated.md",
        3,
        1,
    )
    assert generated["properties"]["placeholder_kind"] == "formula-image"


def test_default_profile_keeps_formula_placeholder_diagnostics_disabled() -> None:
    result = check_documents((doc("<!-- formula-not-decoded -->\n"),), config=Config())

    assert all(diagnostic.code != "GEN004" for diagnostic in result.diagnostics)
