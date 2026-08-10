from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from scieqlint.api import check_documents
from scieqlint.check.references import check_references
from scieqlint.config.model import Config
from scieqlint.diag.model import Severity
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.markdown import markdown_reference_snapshot
from scieqlint.query.host import QueryHost
from scieqlint.scan.markdown import MarkdownScanner


def _scan(text: str):
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        text,
        DocumentKind.MARKDOWN,
    )
    return MarkdownScanner().scan(document, Config())


def _link_tokens(text: str):
    return markdown_reference_snapshot(text).links


def test_missing_reference_is_warning() -> None:
    scan = _scan("See {eq}`missing`.\n")
    diagnostics = check_references(scan.labels, scan.references)
    assert [diagnostic.code for diagnostic in diagnostics] == ["REF002"]
    assert diagnostics[0].severity is Severity.WARNING
    assert diagnostics[0].message == "equation reference target not found: missing"


def test_equation_roles_are_opaque_in_code_math_comments_and_block_html() -> None:
    text = "\n".join(
        [
            "`{eq}code`",
            "$ {eq}`inline-math` $",
            "$$",
            "{eq}`display-math`",
            "$$",
            "<!-- {eq}`comment` -->",
            "<div>",
            "{eq}`raw-html`",
            "",
            "See {eq}`missing`.",
        ]
    )
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [reference.target for reference in legacy.references] == ["missing"]
    assert [reference.target for reference in frontend.equation_refs] == ["missing"]
    assert [
        diagnostic.code for diagnostic in check_references(legacy.labels, legacy.references)
    ] == ["REF002"]


def test_equation_roles_follow_equal_length_and_multiline_code_spans() -> None:
    text = "``{eq}`hidden` ``\nUse ``foo\n{eq}`also-hidden`\nbar`` end.\nSee {eq}`active`."
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [reference.target for reference in legacy.references] == ["active"]
    assert [reference.target for reference in frontend.equation_refs] == ["active"]


def test_escaped_dollar_does_not_make_an_adjacent_role_opaque() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        r"\$ {eq}`active` $ and {eq}`outside`.",
        DocumentKind.MARKDOWN,
    )

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [reference.target for reference in legacy.references] == ["active", "outside"]
    assert [reference.target for reference in frontend.equation_refs] == ["active", "outside"]


@pytest.mark.parametrize(
    ("text", "targets"),
    [
        ("{eq}`before` $x$ {eq}`after`", ["before", "after"]),
        ("\\$ {eq}`after-unclosed`", ["after-unclosed"]),
        (r"\\$ {eq}`inside-even` $", []),
    ],
)
def test_roles_before_after_valid_and_unclosed_math_keep_their_context(
    text: str,
    targets: list[str],
) -> None:
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [reference.target for reference in legacy.references] == targets
    assert [reference.target for reference in frontend.equation_refs] == targets


def test_markdown_link_tokens_reject_blank_line_and_accept_multiline_titles() -> None:
    assert _link_tokens("[x](\n\n)") == ()
    assert _link_tokens("[x](#dest\n\n)") == ()
    assert len(_link_tokens('[x](#dest "title\ncontinued")')) == 1
    assert len(_link_tokens('[x](#dest "title\r\ncontinued")')) == 1
    assert len(_link_tokens('[x](#dest "one\ntwo\nthree")')) == 1
    assert len(_link_tokens('[x](#dest\n "title")')) == 1
    assert len(_link_tokens("[x](#dest (title\ncontinued))")) == 1
    assert _link_tokens("[x](#dest with-space)") == ()
    assert _link_tokens("[x](#dest(with space))") == ()
    assert _link_tokens("[x](#dest\x01)") == ()


def test_roles_in_valid_link_titles_are_opaque_but_invalid_links_are_not() -> None:
    valid = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        '[x](#dest "title\n{eq}`hidden`")\nSee {eq}`active`.',
        DocumentKind.MARKDOWN,
    )
    invalid = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        '[x](#dest\n\n "title\n{eq}`active`")',
        DocumentKind.MARKDOWN,
    )

    valid_snapshot = MySTFrontend().lower((valid,))
    invalid_snapshot = MySTFrontend().lower((invalid,))

    assert [(ref.role_kind, ref.target) for ref in valid_snapshot.generic_refs] == [
        ("markdown-link", "dest")
    ]
    assert [ref.target for ref in valid_snapshot.equation_refs] == ["active"]
    assert [ref.target for ref in invalid_snapshot.equation_refs] == ["active"]


@pytest.mark.parametrize(
    "text",
    [
        "<div>\n{eq}`block-html`",
        "<div>\n{eq}`block-html`\n</div>",
        "<script>\n{eq}`script-html`",
        "<!DOCTYPE html {eq}`declaration`",
        "<?xml {eq}`processing-instruction`",
        "<![CDATA[{eq}`cdata`",
    ],
)
def test_equation_roles_are_opaque_in_unclosed_raw_html_constructs(text: str) -> None:
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert legacy.references == ()
    assert frontend.equation_refs == ()


def test_unclosed_block_html_ends_at_a_blank_line() -> None:
    text = "<div>\n{eq}`hidden`\n\nSee {eq}`active`."
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [reference.target for reference in legacy.references] == ["active"]
    assert [reference.target for reference in frontend.equation_refs] == ["active"]


def test_duplicate_label_is_error() -> None:
    scan = _scan("$$\nE = m c^2\n$$ {#energy}\n\n$$\nF = m a\n$$ {#energy}\n")
    diagnostics = check_references(scan.labels, scan.references)
    assert [diagnostic.code for diagnostic in diagnostics] == ["REF001"]
    assert diagnostics[0].severity is Severity.ERROR


def test_existing_reference_is_quiet() -> None:
    scan = _scan("$$\nE = m c^2\n$$ {#energy}\n\nSee {eq}`energy`.\n")
    assert check_references(scan.labels, scan.references) == ()


def test_latex_missing_reference_warns() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.tex"),
        "See \\eqref{missing}.\n",
        DocumentKind.LATEX,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]
    assert result.diagnostics[0].detail == r"reference text: \eqref{missing}"


def test_cross_format_reference_is_quiet() -> None:
    latex = SourceDocument.from_text(
        PurePosixPath("paper.tex"),
        "See \\eqref{energy}.\n",
        DocumentKind.LATEX,
    )
    markdown = SourceDocument.from_text(
        PurePosixPath("notes.md"),
        "$$\nE = m c^2\n$$ {#energy}\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([latex, markdown], config=Config())

    assert result.diagnostics == ()


def test_markdown_links_to_myst_heading_anchors_are_not_equation_refs() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "\n".join(
            [
                "(intro)=",
                "# Introduction",
                "",
                "(empty-link-target)=",
                "## Empty link target",
                "",
                "See [](#intro) and [#empty-link-target](#empty-link-target).",
            ]
        ),
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert result.diagnostics == ()


@pytest.mark.parametrize(
    ("heading", "expected_codes"),
    [
        ("#", []),
        ("# #", []),
        ("## ##", []),
        ("#Bad", ["STR001", "REF002"]),
    ],
)
def test_myst_anchor_attachment_uses_atx_heading_validity(
    heading: str,
    expected_codes: list[str],
) -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        f"(intro)=\n{heading}\n\nSee [](#intro).\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == expected_codes


def test_markdown_links_to_fenced_directive_anchors_are_not_equation_refs() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "(tip)=\n```{note}\nbody\n```\n\nSee [](#tip).\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert result.diagnostics == ()


def test_only_parsed_markdown_and_myst_references_create_facts() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "Literal \\{eq}`escaped-role`.\n"
        "Literal \\[Eq.](#escaped-link).\n"
        "![equation](#image-target)\n"
        "[site](https://example.invalid/{eq}`destination-target`)\n"
        '[site](https://example.invalid/ "{eq}`title-target`")\n'
        "[See {eq}`active-label`](https://example.invalid/)\n",
        DocumentKind.MARKDOWN,
    )

    snapshot = MySTFrontend().lower((document,))

    assert snapshot.generic_refs == ()
    assert [(ref.ref_kind, ref.target) for ref in snapshot.equation_refs] == [
        ("eq", "active-label")
    ]
    assert ReferenceEngine().run(QueryHost(snapshot)) == ()

    scan = MarkdownScanner().scan(document, Config())
    assert [(ref.source.value, ref.target) for ref in scan.references] == [
        ("myst_eq_role", "active-label")
    ]


def test_link_metadata_uses_balanced_destinations_and_escaped_image_markers() -> None:
    tick = chr(96)
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "[site](https://example.test/a(b){eq}"
        + tick
        + "ghost"
        + tick
        + ")"
        + "\n"
        + "\\![See {eq}"
        + tick
        + "active"
        + tick
        + "](#dest)\n",
        DocumentKind.MARKDOWN,
    )

    snapshot = MySTFrontend().lower((document,))

    assert [(ref.role_kind, ref.target) for ref in snapshot.generic_refs] == [
        ("markdown-link", "dest")
    ]
    assert [(ref.ref_kind, ref.target) for ref in snapshot.equation_refs] == [("eq", "active")]

    scan = MarkdownScanner().scan(document, Config())
    assert [(ref.source.value, ref.target) for ref in scan.references] == [
        ("markdown_anchor", "dest"),
        ("myst_eq_role", "active"),
    ]


def test_even_backslashes_reactivate_markdown_links_and_myst_roles() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "\\\\{eq}`active-role` and \\\\[Eq.](#active-link).\n",
        DocumentKind.MARKDOWN,
    )

    snapshot = MySTFrontend().lower((document,))
    scan = MarkdownScanner().scan(document, Config())

    assert [(ref.ref_kind, ref.target) for ref in snapshot.equation_refs] == [("eq", "active-role")]
    assert [(ref.role_kind, ref.target) for ref in snapshot.generic_refs] == [
        ("markdown-link", "active-link")
    ]
    assert [(ref.source.value, ref.target) for ref in scan.references] == [
        ("markdown_anchor", "active-link"),
        ("myst_eq_role", "active-role"),
    ]


@pytest.mark.parametrize(
    ("text", "targets"),
    [
        (r"\`[active](#active)`", ["active"]),
        (r"\\`[hidden](#hidden)`", []),
        ("$[hidden](#hidden)$", []),
        ("<span>[inline](#inline)</span>", ["inline"]),
        ("<div>\n[hidden](#hidden)\n\n[live](#live)", ["live"]),
    ],
)
def test_link_facts_follow_escaped_code_and_html_ownership(
    text: str,
    targets: list[str],
) -> None:
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    frontend = MySTFrontend().lower((document,))
    legacy = MarkdownScanner().scan(document, Config())

    assert [token.fragment_target for token in _link_tokens(text)] == targets
    assert [ref.target for ref in frontend.generic_refs] == targets
    assert [ref.target for ref in legacy.references] == targets


def test_links_inside_myst_roles_are_not_reparsed_as_markdown() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "{ref}`[role-body](#ghost)`\nSee [live](#live).\n",
        DocumentKind.MARKDOWN,
    )

    frontend = MySTFrontend().lower((document,))
    legacy = MarkdownScanner().scan(document, Config())

    assert [(ref.role_kind, ref.target) for ref in frontend.generic_refs] == [
        ("markdown-link", "live"),
        ("ref", "[role-body](#ghost)"),
    ]
    assert [(ref.source.value, ref.target) for ref in legacy.references] == [
        ("markdown_anchor", "live")
    ]


def test_markdown_link_tokens_preserve_balanced_commonmark_boundaries() -> None:
    valid = (
        "[x](#target)",
        "![alt](#target)",
        '[x]( <https://example.test/a\\>b> "title" )',
        "[x](https://example.test/a(b(c)) 'title')",
        '[x](#target "ti\\"tle")',
        "[x](#target (ti\\(tle\\)))",
        "[x](#target (ti\\)tle))",
        "[x](https://example.test/a\\(b)",
        "[x\ny](#target)",
        "[foo\\\nbar](#target)",
        "[foo\rbar](#target)",
        "[See [the] note](#target)",
        "[See \\] note](#target)",
        "\\![See {eq}`active`](#target)",
    )
    for text in valid:
        tokens = _link_tokens(text)

        assert len(tokens) == 1, text
        token = tokens[0]
        expected = text[2:] if text.startswith("\\!") else text
        assert text[token.start : token.end] == expected, text

    image = _link_tokens("![alt](#target)")[0]
    normal = _link_tokens("[x](#target)")[0]
    assert image.is_image is True
    assert normal.is_image is False
    assert normal.fragment_target == "target"
    assert markdown_reference_snapshot("![alt](#target)").link_metadata_ranges == ((0, 15),)
    assert markdown_reference_snapshot("[x](#target)").link_metadata_ranges == ((4, 12),)

    nested = _link_tokens("[outer [inner](#inner)](#outer)")
    assert len(nested) == 1
    assert nested[0].fragment_target == "inner"

    code = markdown_reference_snapshot("``[x](#hidden)`` and [x](#live)").opaque_ranges
    assert code == tuple(sorted(code))
    assert all(left[1] <= right[0] for left, right in zip(code, code[1:], strict=False))
    assert _link_tokens("[x][ref]") == ()

    invalid = (
        "[x] #target",
        "[x](#target",
        "[x](#target(",
        "[x(#target)",
        "[x](<target\n>)",
        "[x](<a b>)",
        "[x](<target)",
        "[x](<target>",
        "[x](<a<b>)",
        '[x](<dest>"title")',
        '[x](#target "title)',
        '[x](#target "title\n)',
        '[x](#target "title\n  \ncontinued")',
        '[x](#target "title"',
        "[x](#target (title",
        "[x](#target (title\n\ncontinued))",
        "[x](#target (ti(tle)))",
        "[x](#target [title])",
        "\\[x](#target)",
    )
    for text in invalid:
        assert _link_tokens(text) == (), text

    assert _link_tokens("[x](#foo\\-bar)")[0].fragment_target == "foo-bar"
    assert _link_tokens("[x](#a\\)b)")[0].fragment_target == "a)b"
    assert _link_tokens("[x](#foo&amp;bar)")[0].fragment_target == "foo&bar"
    assert _link_tokens("[x](#foo&#x26;bar)")[0].fragment_target == "foo&bar"
    assert _link_tokens("[x](#foo&unknown;)")[0].fragment_target == "foo&unknown;"


def test_fragment_resolution_uses_decoded_destination_and_raw_target_span() -> None:
    text = (
        "[raw](#raw)\n"
        "[escaped](\\#escaped)\n"
        "[angle](<#>)\n"
        "[empty](#)\n"
        "[punct](#foo\\-bar)\n"
        "[paren](#a\\)b)\n"
        "[entity](#foo&amp;bar)\n"
    )
    tokens = _link_tokens(text)

    assert [token.fragment_target for token in tokens] == [
        "raw",
        "escaped",
        None,
        None,
        "foo-bar",
        "a)b",
        "foo&bar",
    ]
    escaped = tokens[1]
    assert escaped.fragment_target_start is not None
    assert escaped.fragment_target_end is not None
    assert text[escaped.fragment_target_start : escaped.fragment_target_end] == "escaped"
    punct = tokens[4]
    assert punct.fragment_target_start is not None
    assert punct.fragment_target_end is not None
    assert text[punct.fragment_target_start : punct.fragment_target_end] == r"foo\-bar"

    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)
    frontend = MySTFrontend().lower((document,))
    legacy = MarkdownScanner().scan(document, Config())

    assert [ref.target for ref in frontend.generic_refs] == [
        "raw",
        "escaped",
        "foo-bar",
        "a)b",
        "foo&bar",
    ]
    assert [ref.target for ref in legacy.references] == [
        "raw",
        "escaped",
        "foo-bar",
        "a)b",
        "foo&bar",
    ]
    assert [
        diagnostic.code for diagnostic in check_references(legacy.labels, legacy.references)
    ] == [
        "REF002",
        "REF002",
        "REF002",
        "REF002",
        "REF002",
    ]


def test_deeply_nested_images_are_parsed_without_recursion() -> None:
    text = "alt"
    for _ in range(600):
        text = f"![{text}](image.png)"

    tokens = _link_tokens(text)

    assert len(tokens) == 1
    assert tokens[0].is_image is True
    assert (tokens[0].start, tokens[0].end) == (0, len(text))


def test_multiline_nested_images_do_not_invalidate_open_frames() -> None:
    text = "alt"
    for _ in range(300):
        text = f"![\n{text}\n](image.png)"

    tokens = _link_tokens(text)

    assert len(tokens) == 1
    assert tokens[0].is_image is True
    assert (tokens[0].start, tokens[0].end) == (0, len(text))


def test_nested_images_preserve_outer_link_semantics_and_image_opacity() -> None:
    image_with_link = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "![foo [bar](#ghost)](img.png)",
        DocumentKind.MARKDOWN,
    )
    link_with_image = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "[![alt](img.png)](#target)",
        DocumentKind.MARKDOWN,
    )

    for document in (image_with_link, link_with_image):
        snapshot = MySTFrontend().lower((document,))
        scan = MarkdownScanner().scan(document, Config())
        if document.text.startswith("!"):
            assert snapshot.generic_refs == ()
            assert scan.references == ()
        else:
            assert [(ref.role_kind, ref.target) for ref in snapshot.generic_refs] == [
                ("markdown-link", "target")
            ]
            assert [(ref.source.value, ref.target) for ref in scan.references] == [
                ("markdown_anchor", "target")
            ]


def test_raw_html_does_not_join_dollar_math_across_live_myst_role() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "<div>\n$$\n</div>\n{eq}`active`\n$$\n",
        DocumentKind.MARKDOWN,
    )

    snapshot = MySTFrontend().lower((document,))
    scan = MarkdownScanner().scan(document, Config())

    assert [(ref.ref_kind, ref.target) for ref in snapshot.equation_refs] == [("eq", "active")]
    assert [(ref.source.value, ref.target) for ref in scan.references] == [
        ("myst_eq_role", "active")
    ]


def test_markdown_links_to_comment_bridged_myst_heading_anchors_are_not_equation_refs() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "(intro)=\n<!-- translator note -->\n# Introduction\n\nSee [](#intro).\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert result.diagnostics == ()


def test_orphaned_myst_anchor_does_not_suppress_markdown_missing_reference() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "(loose-anchor)=\nThis paragraph leaves the anchor unattached.\n\nSee [](#loose-anchor).\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]
    assert result.diagnostics[0].detail == "reference text: [](#loose-anchor)"


def test_check_documents_reports_generic_ref_diagnostics_distinct_from_equation_refs() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "\n".join(
            [
                "(intro)=",
                "# Introduction",
                "",
                "(intro)=",
                "## Duplicate Introduction",
                "",
                "See {ref}`intro`, {ref}`missing`, and {eq}`eq-missing`.",
            ]
        ),
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "REF005",
        "REF004",
        "REF002",
    ]


def test_generated_output_with_dropped_myst_anchor_and_preserved_ref_warns() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("translated/lecture.md"),
        "## A Workaround\n\nSee {ref}`jax_at_workaround`.\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [(diagnostic.code, diagnostic.detail) for diagnostic in result.diagnostics] == [
        ("REF004", "reference text: {ref}`jax_at_workaround`")
    ]


def test_myst_anchor_inside_code_fence_does_not_suppress_markdown_missing_reference() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "```text\n(code-anchor)=\n# Code heading\n```\n\nSee [](#code-anchor).\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]


def test_empty_myst_role_is_malformed_syntax() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        "{ref}`   `\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["DIR011"]
