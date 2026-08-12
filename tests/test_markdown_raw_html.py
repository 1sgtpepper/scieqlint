from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

from scieqlint.api import check_documents, graph_documents
from scieqlint.config.model import ChecksConfig, Config, ScannerConfig, SymbolsConfig
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.markdown import markdown_reference_snapshot, range_contains

_RAW_PAYLOAD = "$$\nx = x + 1\n$$ {#inside}\nSee {eq}`ghost`.\n#Bad\n"

_HTML_BLOCKS = (
    ("type1-style", f"<style>\n{_RAW_PAYLOAD}</style>\n"),
    ("type1-textarea", f"<textarea>\n{_RAW_PAYLOAD}</textarea>\n"),
    ("type2-comment", f"<!--\n{_RAW_PAYLOAD}-->\n"),
    ("type3-processing-instruction", f"<?fixture\n{_RAW_PAYLOAD}?>\n"),
    ("type4-declaration", f"<!FIXTURE\n{_RAW_PAYLOAD}>\n"),
    ("type5-cdata", f"<![CDATA[\n{_RAW_PAYLOAD}]]>\n"),
    ("type6-block-tag", f"<div>\n{_RAW_PAYLOAD}\n"),
    pytest.param(
        "type7-complete-tag",
        f'<x-fixture data-kind="raw">\n{_RAW_PAYLOAD}\n',
        marks=pytest.mark.public_regression,
    ),
)

_HTML_LEAF_LIFECYCLES = (
    ("type1", "<style>", "</style>"),
    ("type2", "<!--", "-->"),
    ("type3", "<?fixture", "?>"),
    ("type4", "<!FIXTURE", ">"),
    ("type5", "<![CDATA[", "]]>"),
)

_TYPE6_TAGS = (
    "address",
    "article",
    "aside",
    "base",
    "basefont",
    "blockquote",
    "body",
    "caption",
    "center",
    "col",
    "colgroup",
    "dd",
    "details",
    "dialog",
    "dir",
    "div",
    "dl",
    "dt",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "frame",
    "frameset",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "head",
    "header",
    "hr",
    "html",
    "iframe",
    "legend",
    "li",
    "link",
    "main",
    "menu",
    "menuitem",
    "nav",
    "noframes",
    "ol",
    "optgroup",
    "option",
    "p",
    "param",
    "search",
    "section",
    "summary",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "title",
    "tr",
    "track",
    "ul",
)


@pytest.mark.parametrize(
    ("family", "source"),
    _HTML_BLOCKS,
    ids=(
        "type1-style",
        "type1-textarea",
        "type2-comment",
        "type3-processing-instruction",
        "type4-declaration",
        "type5-cdata",
        "type6-block-tag",
        "type7-complete-tag",
    ),
)
def test_commonmark_html_block_families_are_opaque(
    family: str,
    source: str,
) -> None:
    document = _document("paper.md", source)

    result = check_documents([document], config=Config())
    graph = graph_documents([document], config=Config())

    assert result.diagnostics == (), family
    assert result.math_blocks_checked == 0, family
    assert graph.nodes == ()
    assert graph.edges == ()


@pytest.mark.parametrize(
    ("family", "opener", "terminator"),
    _HTML_LEAF_LIFECYCLES,
    ids=[family for family, _opener, _terminator in _HTML_LEAF_LIFECYCLES],
)
def test_html_leaf_body_does_not_leak_block_context(
    family: str,
    opener: str,
    terminator: str,
) -> None:
    source = (
        f"{opener}\n"
        "raw paragraph\n"
        "- raw list-looking line\n"
        f"{terminator}\n"
        f'<x-fixture data-kind="raw">\n{_RAW_PAYLOAD}\n'
    )
    document = _document("paper.md", source)
    result = check_documents([document], config=Config())
    graph = graph_documents([document], config=Config())

    assert result.diagnostics == (), family
    assert result.math_blocks_checked == 0, family
    assert graph.nodes == ()
    assert graph.edges == ()


@pytest.mark.parametrize("tag", _TYPE6_TAGS)
def test_every_commonmark_type6_tag_owns_its_block(tag: str) -> None:
    source = f"<{tag}>\n{_RAW_PAYLOAD}\n"
    snapshot = markdown_reference_snapshot(source)

    assert range_contains(source.index("x = x + 1"), snapshot.opaque_ranges)
    assert range_contains(source.index("{eq}`ghost`"), snapshot.opaque_ranges)


def test_type6_closing_tag_starts_a_block() -> None:
    source = f"</SEARCH> trailing text\n{_RAW_PAYLOAD}\n"
    result = check_documents([_document("paper.md", source)], config=Config())

    assert result.diagnostics == ()
    assert result.math_blocks_checked == 0


def test_type1_ends_on_the_first_type1_closing_tag_line() -> None:
    source = f"<style>\n{_RAW_PAYLOAD}</textarea> #Bad remains raw HTML\n$$\nx = x + 1\n$$\n"
    result = check_documents([_document("paper.md", source)], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["ALG001"]
    assert result.diagnostics[0].span is not None
    assert result.diagnostics[0].span.line == 9


def test_type6_continues_past_a_same_tag_close_until_blank_line() -> None:
    source = f"<div>\n{_RAW_PAYLOAD}</div>\nSee {{eq}}`still-raw`.\n#StillRaw\n\n"
    result = check_documents([_document("paper.md", source)], config=Config())

    assert result.diagnostics == ()
    assert result.math_blocks_checked == 0


def test_list_type1_html_keeps_unindented_blank_inside_the_leaf() -> None:
    source = (
        "- <style>\n"
        "\n"
        "  $$\n"
        "  x = x + 1\n"
        "  $$ {#inside}\n"
        "  See {eq}`ghost`.\n"
        "  #Bad\n"
        "  </style>\n"
        "$$\n"
        "x = x + 1\n"
        "$$\n"
    )
    document = _document("paper.md", source)
    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["ALG001"]
    assert result.math_blocks_checked == 1


def test_list_html_terminating_on_opener_releases_following_markdown() -> None:
    source = "- <style>raw HTML</style>\n$$\nx = x + 1\n$$\n"
    snapshot = markdown_reference_snapshot(source)
    result = check_documents([_document("paper.md", source)], config=Config())

    assert range_contains(source.index("raw HTML"), snapshot.opaque_ranges)
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["ALG001"]
    assert result.math_blocks_checked == 1


@pytest.mark.parametrize(
    "opener",
    ["<div>", "<x-fixture>"],
    ids=("type6", "type7"),
)
def test_list_type6_and_type7_end_before_an_unindented_blank(opener: str) -> None:
    source = (
        f"- {opener}\n"
        "  $$\n"
        "  x = x + 1\n"
        "  $$ {#inside}\n"
        "  See {eq}`ghost`.\n"
        "  #Bad\n"
        "\n"
        "$$\n"
        "x = x + 1\n"
        "$$\n"
    )
    result = check_documents([_document("paper.md", source)], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["ALG001"]
    assert result.math_blocks_checked == 1


def test_type7_complete_tag_does_not_interrupt_a_paragraph() -> None:
    source = f"paragraph\n<x-fixture data-kind=raw>\n{_RAW_PAYLOAD}\n"
    result = check_documents([_document("paper.md", source)], config=Config())

    assert {diagnostic.code for diagnostic in result.diagnostics} == {
        "ALG001",
        "REF002",
        "STR001",
    }
    assert result.math_blocks_checked == 1


@pytest.mark.parametrize(
    "tag",
    ["<x-fixture =raw>", "<x:fixture>"],
)
def test_incomplete_type7_candidate_does_not_own_following_markdown(tag: str) -> None:
    source = f"{tag}\n{_RAW_PAYLOAD}\n"
    result = check_documents([_document("paper.md", source)], config=Config())

    assert {diagnostic.code for diagnostic in result.diagnostics} == {
        "ALG001",
        "REF002",
        "STR001",
    }
    assert result.math_blocks_checked == 1


def test_type6_tag_interrupts_a_paragraph() -> None:
    source = f"paragraph\n<div>\n{_RAW_PAYLOAD}\n"
    result = check_documents([_document("paper.md", source)], config=Config())

    assert result.diagnostics == ()
    assert result.math_blocks_checked == 0


@pytest.mark.parametrize(
    "source",
    [
        "> <style>\n> raw HTML\n$$\nx = x + 1\n$$\n",
        "- <style>\n  raw HTML\n$$\nx = x + 1\n$$\n",
        "  > <style>\n  > $$\n  > x = x + 1\n  > $$\n$$\nx = x + 1\n$$\n",
    ],
    ids=("block-quote", "list-item", "indented-block-quote"),
)
def test_unclosed_html_block_stops_at_its_container_boundary(source: str) -> None:
    result = check_documents([_document("paper.md", source)], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["ALG001"]
    assert result.math_blocks_checked == 1


def test_top_level_html_leaf_keeps_quote_markers_in_its_payload() -> None:
    source = (
        "<style>\n"
        "> $$\n"
        "> x = x + 1\n"
        "> $$ {#inside}\n"
        "> See {eq}`ghost`.\n"
        "</style>\n"
        "$$\n"
        "x = x + 1\n"
        "$$\n"
    )
    snapshot = markdown_reference_snapshot(source)
    result = check_documents([_document("paper.md", source)], config=Config())

    assert range_contains(source.index("> $$"), snapshot.opaque_ranges)
    assert range_contains(source.index("{eq}`ghost`"), snapshot.opaque_ranges)
    assert range_contains(source.index("</style>"), snapshot.opaque_ranges)
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["ALG001"]
    assert result.math_blocks_checked == 1


def test_quoted_html_leaf_accepts_nested_quote_markers_until_boundary() -> None:
    source = (
        "> <style>\n"
        "> > $$\n"
        "> > x = x + 1\n"
        "> > $$ {#inside}\n"
        "> > See {eq}`ghost`.\n"
        "outside boundary\n"
        "$$\n"
        "x = x + 1\n"
        "$$\n"
    )
    snapshot = markdown_reference_snapshot(source)
    result = check_documents([_document("paper.md", source)], config=Config())

    assert range_contains(source.index("> > $$"), snapshot.opaque_ranges)
    assert range_contains(source.index("{eq}`ghost`"), snapshot.opaque_ranges)
    assert not range_contains(source.index("outside boundary"), snapshot.opaque_ranges)
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["ALG001"]
    assert result.math_blocks_checked == 1


def test_inline_html_is_opaque_but_text_between_tags_remains_active() -> None:
    source = (
        "before <!-- $$ x = x + 1 $$ {eq}`comment` --> after\n"
        '<span data-ref="{eq}`attribute`">See {eq}`visible`.</span>\n'
    )
    result = check_documents([_document("paper.md", source)], config=Config())

    assert [(diagnostic.code, diagnostic.message) for diagnostic in result.diagnostics] == [
        ("REF002", "equation reference target not found: visible")
    ]


@pytest.mark.parametrize(
    "comment",
    ["<!-->", "<!--->"],
    ids=("empty-short-comment", "hyphen-short-comment"),
)
def test_inline_html_short_comment_is_opaque(comment: str) -> None:
    source = f"before {comment} after {{eq}}`visible`.\n"
    snapshot = markdown_reference_snapshot(source)
    result = check_documents([_document("paper.md", source)], config=Config())

    assert range_contains(source.index(comment), snapshot.opaque_ranges)
    assert not range_contains(source.index("after"), snapshot.opaque_ranges)
    assert [(diagnostic.code, diagnostic.message) for diagnostic in result.diagnostics] == [
        ("REF002", "equation reference target not found: visible")
    ]


@pytest.mark.parametrize("quote", ['"', "'"], ids=("double-quoted", "single-quoted"))
def test_inline_html_quoted_attribute_keeps_markup_and_math_opaque(quote: str) -> None:
    source = (
        f"before <span data={quote}<em> {{eq}}`inside` $x$ {quote}>after {{eq}}`visible`.</span>\n"
    )
    snapshot = markdown_reference_snapshot(source)
    result = check_documents(
        [_document("paper.md", source)],
        config=Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert range_contains(source.index("{eq}`inside`"), snapshot.opaque_ranges)
    assert range_contains(source.index("$x$"), snapshot.opaque_ranges)
    assert not range_contains(source.index("after"), snapshot.opaque_ranges)
    assert result.math_blocks_checked == 0
    assert [(diagnostic.code, diagnostic.message) for diagnostic in result.diagnostics] == [
        ("REF002", "equation reference target not found: visible")
    ]


def test_inline_html_attribute_allows_one_line_ending() -> None:
    source = (
        'before <span data="a <em> {eq}`inside` $x$"\n'
        '  data-two="b > c">after {eq}`visible`.</span>\n'
    )
    snapshot = markdown_reference_snapshot(source)
    result = check_documents(
        [_document("paper.md", source)],
        config=Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert range_contains(source.index("{eq}`inside`"), snapshot.opaque_ranges)
    assert range_contains(source.index("$x$"), snapshot.opaque_ranges)
    assert not range_contains(source.index("after"), snapshot.opaque_ranges)
    assert result.math_blocks_checked == 0
    assert [(diagnostic.code, diagnostic.message) for diagnostic in result.diagnostics] == [
        ("REF002", "equation reference target not found: visible")
    ]


def test_inline_html_valid_closing_tag_is_opaque() -> None:
    source = "before </span > after {eq}`visible`.\n"
    snapshot = markdown_reference_snapshot(source)
    result = check_documents([_document("paper.md", source)], config=Config())

    assert range_contains(source.index("</span"), snapshot.opaque_ranges)
    assert not range_contains(source.index("after"), snapshot.opaque_ranges)
    assert [(diagnostic.code, diagnostic.message) for diagnostic in result.diagnostics] == [
        ("REF002", "equation reference target not found: visible")
    ]


@pytest.mark.parametrize(
    "tag",
    [
        '<span:fixture data="{eq}`inside` $x$">',
        '<span h*ref="{eq}`inside` $x$">',
        '</span href="{eq}`inside` $x$">',
        "<span data=bad{eq}`inside`$x$>",
        '<span data="{eq}`inside` $x$>',
        '<span data="{eq}`inside` $x$"',
    ],
    ids=(
        "colon-tag-name",
        "punctuated-attribute-name",
        "closing-tag-attributes",
        "forbidden-unquoted-character",
        "missing-closing-quote",
        "missing-closing-angle",
    ),
)
def test_invalid_inline_html_tag_keeps_markdown_active(tag: str) -> None:
    source = f"before {tag} after {{eq}}`outside`.\n"
    snapshot = markdown_reference_snapshot(source)
    result = check_documents(
        [_document("paper.md", source)],
        config=Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert not range_contains(source.index("{eq}`inside`"), snapshot.opaque_ranges)
    assert result.math_blocks_checked == 1
    assert [diagnostic.message for diagnostic in result.diagnostics] == [
        "equation reference target not found: inside",
        "equation reference target not found: outside",
    ]


@pytest.mark.parametrize(
    "opener",
    ["<!--", "<?fixture", "<!DOCTYPE", "<![CDATA["],
    ids=("comment", "processing-instruction", "declaration", "cdata"),
)
def test_unterminated_inline_html_construct_keeps_markdown_active(opener: str) -> None:
    source = f"before {opener} {{eq}}`visible`"
    snapshot = markdown_reference_snapshot(source)
    result = check_documents([_document("paper.md", source)], config=Config())

    assert not range_contains(source.index("{eq}`visible`"), snapshot.opaque_ranges)
    assert [(diagnostic.code, diagnostic.message) for diagnostic in result.diagnostics] == [
        ("REF002", "equation reference target not found: visible")
    ]


@pytest.mark.parametrize(
    ("opener", "terminator"),
    [
        ("<!--", "-->"),
        ("<?fixture", "?>"),
        ("<!DOCTYPE", ">"),
        ("<![CDATA[", "]]>"),
        ('<span data="unfinished', '">'),
    ],
    ids=("comment", "processing-instruction", "declaration", "cdata", "quoted-tag"),
)
def test_unterminated_inline_html_stops_at_a_blank_line_boundary(
    opener: str,
    terminator: str,
) -> None:
    source = f"before {opener}\n\nSee {{eq}}`after`.\n$$\nx = x + 1\n$$\n{terminator}\n"
    snapshot = markdown_reference_snapshot(source)
    result = check_documents([_document("paper.md", source)], config=Config())

    assert not range_contains(source.index(opener), snapshot.opaque_ranges)
    assert not range_contains(source.index("{eq}`after`"), snapshot.opaque_ranges)
    assert {diagnostic.code for diagnostic in result.diagnostics} == {"ALG001", "REF002"}
    assert result.math_blocks_checked == 1


def test_inline_html_stops_at_a_block_quote_boundary() -> None:
    source = "> before <!--\n# Outside\nSee {eq}`after`.\n$$\nx = x + 1\n$$\n-->\n"
    snapshot = markdown_reference_snapshot(source)
    result = check_documents([_document("paper.md", source)], config=Config())

    assert not range_contains(source.index("<!--"), snapshot.opaque_ranges)
    assert not range_contains(source.index("{eq}`after`"), snapshot.opaque_ranges)
    assert {diagnostic.code for diagnostic in result.diagnostics} == {"ALG001", "REF002"}
    assert result.math_blocks_checked == 1


def test_html_comment_suppression_directive_remains_active() -> None:
    source = "<!-- scieqlint-disable-next-line ALG001 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n"
    result = check_documents([_document("paper.md", source)], config=Config())

    assert [(diagnostic.code, diagnostic.suppressed) for diagnostic in result.diagnostics] == [
        ("ALG001", True)
    ]
    assert result.exit_code() == 0


def test_html_comment_symbol_directive_remains_active() -> None:
    source = "<!-- scieqlint-symbol: E = energy -->\n$$\nE = E\n$$\n"
    config = Config(checks=ChecksConfig(symbols=SymbolsConfig(enabled=True)))
    result = check_documents([_document("paper.md", source)], config=config)

    assert result.diagnostics == ()


def test_notebook_markdown_cells_share_raw_html_opacity() -> None:
    notebook = json.dumps(
        {
            "cells": [
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": f"<style>\n{_RAW_PAYLOAD}</style>\n",
                }
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
    )
    document = SourceDocument.from_text(
        PurePosixPath("paper.ipynb"), notebook, DocumentKind.NOTEBOOK
    )

    result = check_documents([document], config=Config())
    graph = graph_documents([document], config=Config())

    assert result.diagnostics == ()
    assert result.math_blocks_checked == 0
    assert graph.nodes == ()
    assert graph.edges == ()


def _document(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)
