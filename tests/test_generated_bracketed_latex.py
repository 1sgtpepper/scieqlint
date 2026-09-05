from __future__ import annotations

from pathlib import Path, PurePosixPath

from scieqlint.app import check_documents
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.markdown import _markdown_line_ownership_for_generated
from scieqlint.parse.math import MathHost
from scieqlint.report.text import TextReporter


def doc(text: str, *, origin: SourceOrigin | None = None) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("generated.md"),
        text,
        DocumentKind.MARKDOWN,
        origin=origin,
    )


def bracketed_facts(text: str):
    return tuple(
        fact
        for fact in MathHost().classify(MySTFrontend().lower((doc(text),))).generated_formulas
        if fact.kind == "bracketed-block"
    )


def test_bracketed_latex_blocks_preserve_complete_same_line_and_eof_spans() -> None:
    source = "Intro.\n\n\\[\nx = y\n\\]\n\\[ z = 1 \\]\n\\[\nunterminated"

    facts = bracketed_facts(source)

    assert [fact.complete for fact in facts] == [True, True, False]
    assert [source[fact.span.start : fact.span.end] for fact in facts if fact.span] == [
        "\\[\nx = y\n\\]",
        "\\[ z = 1 \\]",
        "\\[\nunterminated",
    ]
    assert [fact.text for fact in facts] == [
        "\\[\nx = y\n\\]",
        "\\[ z = 1 \\]",
        "\\[\nunterminated",
    ]


def test_representative_generated_fixture_covers_literal_wrapper_raw_fact_and_diagnostic() -> None:
    source = (
        Path(__file__)
        .parent.joinpath("fixtures/generated/bracketed_latex.md")
        .read_text(encoding="utf-8")
    )
    generated = SourceDocument.from_text(
        PurePosixPath("tests/fixtures/generated/bracketed_latex.md"),
        source,
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(source_document_id="source/formulas.pdf"),
    )

    frontend = MySTFrontend().lower((generated,))
    assert [
        (fact.kind, fact.candidate_kind, fact.complete, fact.delimiter_kind, fact.raw)
        for fact in frontend.generated_formulas
        if fact.candidate_kind == "bracketed-block"
    ] == [
        (
            "candidate",
            "bracketed-block",
            True,
            "literal",
            "[\n\\begin{array}{cc}\nx & y \\\\\n\\end{array}\n]",
        )
    ]

    classified = MathHost().classify(frontend)
    assert [
        (fact.kind, fact.delimiter_kind)
        for fact in classified.generated_formulas
        if fact.kind == "bracketed-block"
    ] == [("bracketed-block", "literal")]

    result = check_documents(
        (generated,),
        config=Config(profile=ProfileConfig(name="generated-myst")),
    )
    diagnostics = tuple(
        diagnostic for diagnostic in result.diagnostics if diagnostic.code == "GEN003"
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].detail == (
        "standalone [...] display delimiters are not portable generated Markdown"
    )
    assert diagnostics[0].properties[:3] == (
        ("formula_artifact_kind", "bracketed-block"),
        ("complete", "true"),
        ("delimiter_kind", "literal"),
    )
    assert diagnostics[0].provenance_ids == (
        "tests/fixtures/generated/bracketed_latex.md::generated-provenance",
    )
    assert diagnostics[0].span is not None
    assert source[diagnostics[0].span.start : diagnostics[0].span.end] == (
        "[\n\\begin{array}{cc}\nx & y \\\\\n\\end{array}\n]"
    )
    assert TextReporter().render(result) == Path(
        "tests/golden/text/generated_bracketed_latex_fixture.txt"
    ).read_text(encoding="utf-8")


def test_bracketed_latex_close_only_starts_an_adjacent_block_when_owned() -> None:
    source = "Intro.\n\\]\n\\[ x = y \\]\n"

    assert bracketed_facts(source) == ()


def test_bracketed_latex_close_boundary_does_not_skip_intervening_prose() -> None:
    source = "\\[ x = y \\]\nprose\n\\[ z = 1 \\]\n"

    facts = bracketed_facts(source)

    assert [fact.text for fact in facts] == ["\\[ x = y \\]"]


def test_bracketed_latex_close_boundary_preserves_container_ownership() -> None:
    cases = (
        (
            "- \\[ x\n  \\]\n  \\[ y \\]\n",
            ("\\[ x\n  \\]", "\\[ y \\]"),
        ),
        (
            "> \\[ x\n> \\]\n> \\[ y \\]\n",
            ("\\[ x\n> \\]", "\\[ y \\]"),
        ),
    )

    for source, expected in cases:
        facts = bracketed_facts(source)

        assert [fact.text for fact in facts] == list(expected)


def test_bracketed_latex_blocks_use_list_and_blockquote_content_offsets() -> None:
    source = "- \\[\n  x = y\n  \\]\n\n> \\[\n> a = b\n> \\]\n"

    facts = bracketed_facts(source)

    assert [(fact.complete, source[fact.span.start : fact.span.end]) for fact in facts] == [
        (True, "\\[\n  x = y\n  \\]"),
        (True, "\\[\n> a = b\n> \\]"),
    ]
    assert [(fact.span.line, fact.span.col) for fact in facts if fact.span is not None] == [
        (1, 3),
        (5, 3),
    ]


def test_bracketed_latex_blocks_preserve_tab_nested_list_source_offsets() -> None:
    cases = (
        ("- outer\n\t- \\[ x = y \\]\n", "\\[ x = y \\]"),
        ("- outer\n\n\t\\[ z = q \\]\n", "\\[ z = q \\]"),
        ("> - outer\n> \t- \\[ a = b \\]\n", "\\[ a = b \\]"),
    )

    for source, expected in cases:
        facts = bracketed_facts(source)

        assert [(fact.complete, fact.text) for fact in facts] == [(True, expected)]
        [fact] = facts
        assert fact.span is not None
        start = source.index(expected)
        assert (fact.span.start, fact.span.end) == (start, start + len(expected))
        assert source[fact.span.start : fact.span.end] == expected


def test_markdown_line_ownership_preserves_tab_expansion_source_offsets() -> None:
    cases = (
        ("plain\n", "plain"),
        ("- nested\n", "nested"),
        ("- outer\n  - nested\n", "nested"),
        ("- outer\n\t- nested\n", "nested"),
        ("1. outer\n\t- nested\n", "nested"),
        ("> - outer\n> \t- nested\n", "nested"),
        ("> > - outer\n> > \t- nested\n", "nested"),
        ("-   outer\n\t- nested\n", "nested"),
        ("- outer\n  -\tnested\n", "nested"),
        ("- outer\n\n\tstandalone\n", "standalone"),
    )

    for source, expected in cases:
        (
            content_start,
            content,
            _container_key,
            _block_start,
            _block_end,
            _text_role,
        ) = _markdown_line_ownership_for_generated(source)[-1]

        expected_start = source.rindex(expected)
        assert content_start == expected_start
        assert content == expected
        assert source[content_start : content_start + len(content)] == content


def test_tab_indented_list_continuation_is_not_a_standalone_bracketed_block() -> None:
    assert bracketed_facts("- outer\n\t\\[ x = y \\]\n") == ()


def test_bracketed_latex_multiline_blocks_stop_at_container_boundaries() -> None:
    cases = (
        ("- \\[\n  x = y\n- \\]\n", "\\[\n  x = y\n"),
        ("> \\[\n> x = y\n\n\\]\n", "\\[\n> x = y\n"),
    )

    for source, expected in cases:
        facts = bracketed_facts(source)

        assert [(fact.complete, source[fact.span.start : fact.span.end]) for fact in facts] == [
            (False, expected)
        ]


def test_bracketed_latex_multiline_blocks_stop_before_owned_content() -> None:
    source = "\\[\nx = y\n`owned`\n\\]\n"

    facts = bracketed_facts(source)

    assert [(fact.complete, source[fact.span.start : fact.span.end]) for fact in facts] == [
        (False, "\\[\nx = y\n")
    ]


def test_bracketed_latex_root_blocks_stop_at_new_markdown_blocks() -> None:
    cases = (
        ("\\[\nx = y\n# Heading\n\\]\n", "\\[\nx = y\n"),
        ("\\[\nx = y\n---\n\\]\n", "\\[\nx = y\n"),
        ("\\[\nx = y\n```text\nignored\n```\n\\]\n", "\\[\nx = y\n"),
        ("\\[\nx = y\n<style>\nignored\n</style>\n\\]\n", "\\[\nx = y\n"),
        ("\\[\nx = y\n\nnext paragraph\n\\]\n", "\\[\nx = y\n\n"),
    )

    for source, expected in cases:
        facts = bracketed_facts(source)

        assert [(fact.complete, source[fact.span.start : fact.span.end]) for fact in facts] == [
            (False, expected)
        ]


def test_bracketed_latex_root_blocks_allow_continuations_and_blank_lines() -> None:
    cases = (
        ("\\[\nx = y\nz = q\n\\]\n", "\\[\nx = y\nz = q\n\\]"),
        ("\\[\nx = y\n\n\\]\n", "\\[\nx = y\n\n\\]"),
    )

    for source, expected in cases:
        facts = bracketed_facts(source)

        assert [(fact.complete, source[fact.span.start : fact.span.end]) for fact in facts] == [
            (True, expected)
        ]


def test_bracketed_latex_blocks_start_after_markdown_boundaries_without_blank_lines() -> None:
    cases = (
        ("# Heading\n\\[ x = y \\]\n", "\\[ x = y \\]"),
        ("---\n\\[ x = y \\]\n", "\\[ x = y \\]"),
        ("```text\nignored\n```\n\\[ x = y \\]\n", "\\[ x = y \\]"),
        ("<!--\nignored\n-->\n\\[ x = y \\]\n", "\\[ x = y \\]"),
        ("<style>\nignored\n</style>\n[\n\\alpha\n]\n", "[\n\\alpha\n]"),
        ("$$\nignored\n$$\n[\n\\alpha\n]\n", "[\n\\alpha\n]"),
    )

    for source, expected in cases:
        facts = bracketed_facts(source)

        assert [fact.text for fact in facts] == [expected]


def test_bracketed_latex_blocks_do_not_reinterpret_multiline_markdown_links() -> None:
    cases = (
        "[\n\\alpha + \\beta\n](https://example.invalid)\n",
        "[\n\\alpha + \\beta\n](\nhttps://example.invalid\n)\n",
        "[\n\\alpha + \\beta\n]: https://example.invalid\n",
    )

    for source in cases:
        assert bracketed_facts(source) == ()


def test_literal_bracket_wrappers_require_a_latex_signal() -> None:
    cases = (
        "[\nordinary text\n]\n",
        "[\nversion = 2026\n]\n",
        "[\npage = 12\n]\n",
        "[\nenergy = m c^2\n]\n",
        "[x = y]\n",
        "[label](https://example.invalid)\n",
        "[\nplain label\n]\n",
    )

    for source in cases:
        assert bracketed_facts(source) == ()


def test_literal_bracket_wrapper_accepts_a_concise_equation_body() -> None:
    for source in ("[\nx = y\n]\n", "[\nx = 2\n]\n"):
        facts = bracketed_facts(source)

        assert [(fact.complete, fact.text) for fact in facts] == [(True, source[:-1])]


def test_literal_bracket_wrapper_reaches_eof_as_incomplete() -> None:
    source = "[\n\\begin{array}{cc}\nx & y"

    facts = bracketed_facts(source)

    assert [(fact.complete, fact.text) for fact in facts] == [(False, source)]


def test_bracketed_latex_container_blocks_stop_at_new_markdown_blocks() -> None:
    cases = (
        ("- \\[\n  x = y\n  # Heading\n  \\]\n", "\\[\n  x = y\n"),
        ("- \\[\n  x = y\n\n  next paragraph\n  \\]\n", "\\[\n  x = y\n\n"),
        ("> \\[\n> x = y\n> # Heading\n> \\]\n", "\\[\n> x = y\n"),
        ("> \\[\n> x = y\n> ---\n> \\]\n", "\\[\n> x = y\n"),
    )

    for source, expected in cases:
        facts = bracketed_facts(source)

        assert [(fact.complete, source[fact.span.start : fact.span.end]) for fact in facts] == [
            (False, expected)
        ]


def test_bracketed_latex_container_blocks_allow_continuations_and_blank_closers() -> None:
    cases = (
        ("- \\[\n  x = y\n  z = q\n  \\]\n", "\\[\n  x = y\n  z = q\n  \\]"),
        ("> \\[\n> x = y\n>\n> \\]\n", "\\[\n> x = y\n>\n> \\]"),
    )

    for source, expected in cases:
        facts = bracketed_facts(source)

        assert [(fact.complete, source[fact.span.start : fact.span.end]) for fact in facts] == [
            (True, expected)
        ]


def test_bracketed_latex_list_opener_reaches_eof_as_incomplete() -> None:
    source = "- \\[\n  x = y"

    facts = bracketed_facts(source)

    assert len(facts) == 1
    assert facts[0].complete is False
    assert facts[0].span is not None
    assert source[facts[0].span.start : facts[0].span.end] == "\\[\n  x = y"


def test_frontend_keeps_bracketed_blocks_as_candidates_until_math_host() -> None:
    source = doc("\\[\nx = y\n\\]\n")

    frontend = MySTFrontend().lower((source,))
    assert [(fact.kind, fact.candidate_kind) for fact in frontend.generated_formulas] == [
        ("candidate", "bracketed-block")
    ]

    classified = MathHost().classify(frontend)
    assert [(fact.kind, fact.candidate_kind) for fact in classified.generated_formulas] == [
        ("bracketed-block", None)
    ]


def test_bracketed_scanner_excludes_owned_math_code_inline_and_nonstandalone_text() -> None:
    source = """\
Text \\[ x = y \\] stays prose.

`\\[`

```text
\\[
x = y
\\]
```

$$
\\[
x = y
\\]
$$

\\\\[
not an opener
\\\\]
"""

    assert bracketed_facts(source) == ()


def test_empty_owned_math_does_not_block_later_bracketed_math() -> None:
    source = "```math\n```\n\n\\[ x = y \\]\n"

    facts = bracketed_facts(source)

    assert [fact.text for fact in facts] == ["\\[ x = y \\]"]


def test_bracketed_latex_continuing_prose_is_not_a_generated_diagnostic() -> None:
    source = "Intro text\n\\[ x = y\n\\]\n"
    config = Config(profile=ProfileConfig(name="generated-myst"))

    result = check_documents(
        (doc(source, origin=SourceOrigin(source_document_id="source/formulas.tex")),),
        config=config,
    )
    assert [
        diagnostic.code for diagnostic in result.diagnostics if diagnostic.code == "GEN003"
    ] == []

    control = check_documents(
        (doc("\\[ x = y\n\\]\n", origin=SourceOrigin(source_document_id="source/formulas.tex")),),
        config=config,
    )
    assert [
        diagnostic.code for diagnostic in control.diagnostics if diagnostic.code == "GEN003"
    ] == ["GEN003"]


def test_nested_openers_have_one_owner_and_close_at_the_first_standalone_closer() -> None:
    source = "\\[\nouter\n\\[\ninner\n\\]\nafter\n\\]\n"

    facts = bracketed_facts(source)

    assert len(facts) == 1
    assert facts[0].complete is True
    assert facts[0].span is not None
    assert source[facts[0].span.start : facts[0].span.end] == "\\[\nouter\n\\[\ninner\n\\]"


def test_bracketed_opener_with_inline_content_can_close_on_a_later_line() -> None:
    source = "\\[ x = y\n\\]\n"

    facts = bracketed_facts(source)

    assert [(fact.complete, source[fact.span.start : fact.span.end]) for fact in facts] == [
        (True, "\\[ x = y\n\\]")
    ]


def test_same_line_bracketed_close_requires_odd_escape_parity() -> None:
    even = "\\" * 2
    odd = "\\" * 3

    even_source = f"\\[ x {even}]"
    odd_source = f"\\[ x {odd}]"

    [even_fact] = bracketed_facts(even_source)
    [odd_fact] = bracketed_facts(odd_source)

    assert even_fact.complete is False
    assert even_source[even_fact.span.start : even_fact.span.end] == even_source
    assert odd_fact.complete is True
    assert odd_source[odd_fact.span.start : odd_fact.span.end] == odd_source


def test_same_line_bracketed_close_ignores_active_tex_comments() -> None:
    commented_source = r"\[ x = 1 % \]"
    escaped_percent_source = r"\[ x = 1 \% \]"

    [commented] = bracketed_facts(commented_source)
    [escaped_percent] = bracketed_facts(escaped_percent_source)

    assert commented.complete is False
    assert escaped_percent.complete is True


def test_generated_profile_emits_complete_and_incomplete_diagnostics_in_source_order() -> None:
    source = "\\[\nx = y\n\\]\n\n\\[\nunterminated"

    result = check_documents(
        (
            doc(
                source,
                origin=SourceOrigin(source_document_id="source/formulas.tex"),
            ),
        ),
        config=Config(profile=ProfileConfig(name="generated-myst")),
    )
    diagnostics = tuple(
        diagnostic for diagnostic in result.diagnostics if diagnostic.code == "GEN003"
    )

    assert [diagnostic.detail for diagnostic in diagnostics] == [
        "standalone \\[...\\] display delimiters are not portable generated Markdown",
        "standalone \\[ display container is incomplete",
    ]
    assert [dict(diagnostic.properties)["complete"] for diagnostic in diagnostics] == [
        "true",
        "false",
    ]
    assert [dict(diagnostic.properties)["delimiter_kind"] for diagnostic in diagnostics] == [
        "escaped",
        "escaped",
    ]
    assert all(
        diagnostic.provenance_ids == ("generated.md::generated-provenance",)
        for diagnostic in diagnostics
    )
    assert TextReporter().render(result) == Path(
        "tests/golden/text/generated_bracketed_latex.txt"
    ).read_text(encoding="utf-8")


def test_generated_profile_uses_boundary_neutral_detail_for_incomplete_containers() -> None:
    cases = (
        "- \\[\n  x = y\n- \\]\n",
        "> \\[\n> x = y\n\n\\]\n",
        "\\[\nx = y\n`owned`\n\\]\n",
    )

    for source in cases:
        result = check_documents(
            (doc(source),),
            config=Config(profile=ProfileConfig(name="generated-myst")),
        )
        diagnostics = tuple(
            diagnostic for diagnostic in result.diagnostics if diagnostic.code == "GEN003"
        )

        assert len(diagnostics) == 1
        assert diagnostics[0].detail == "standalone \\[ display container is incomplete"
        assert dict(diagnostics[0].properties)["complete"] == "false"
        assert dict(diagnostics[0].properties)["delimiter_kind"] == "escaped"


def test_default_profile_does_not_emit_bracketed_generated_diagnostic() -> None:
    result = check_documents((doc("\\[\nx=y\n\\]\n"),), config=Config())

    assert all(diagnostic.code != "GEN003" for diagnostic in result.diagnostics)
