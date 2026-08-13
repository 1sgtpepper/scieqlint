from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path, PurePosixPath

import pytest

from scieqlint import markdown as markdown_module
from scieqlint.api import check_documents, graph_documents
from scieqlint.check.references import check_references
from scieqlint.config.model import Config, ScannerConfig
from scieqlint.diag.model import Diagnostic, Severity, SourceSpan
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost
from scieqlint.scan.markdown import MarkdownScanner


class _CharacterWorkText(str):
    def __new__(cls, value: str):
        instance = super().__new__(cls, value)
        instance.character_work = 0
        return instance

    def __getitem__(self, key):
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            self.character_work += len(range(start, stop, step))
        else:
            self.character_work += 1
        return super().__getitem__(key)

    def find(self, sub: str, start: int = 0, end: int | None = None) -> int:
        search_end = len(self) if end is None else end
        self.character_work += max(0, search_end - start)
        return super().find(sub, start, search_end)


class _RangeWork(tuple[tuple[int, int], ...]):
    def __new__(cls, ranges: tuple[tuple[int, int], ...]):
        instance = super().__new__(cls, ranges)
        instance.item_reads = 0
        return instance

    def __iter__(self):
        for item in super().__iter__():
            self.item_reads += 1
            yield item

    def __getitem__(self, index):
        self.item_reads += 1
        return super().__getitem__(index)


class _CopyCountingList(list[object]):
    copied_items = 0

    def extend(self, values: Iterable[object]) -> None:
        items = tuple(values)
        type(self).copied_items += len(items)
        super().extend(items)


def _scan(text: str):
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        text,
        DocumentKind.MARKDOWN,
    )
    return MarkdownScanner().scan(document, Config())


def _link_tokens(text: str):
    return markdown_module.markdown_reference_snapshot(text).links


def _reference_targets(text: str) -> tuple[list[str], list[str], list[str]]:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        text,
        DocumentKind.MARKDOWN,
    )
    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))
    graph = graph_documents([document], config=Config())
    return (
        [reference.target for reference in legacy.references],
        [reference.target for reference in frontend.generic_refs],
        [node.label for node in graph.nodes if node.kind == "reference"],
    )


def test_entity_decoding_bounds_ampersand_character_work() -> None:
    source = _CharacterWorkText("[label](#" + "&" * 2_048 + ")")

    tokens = markdown_module.markdown_reference_snapshot(source).links

    assert len(tokens) == 1
    assert source.character_work <= 100 * len(source)


@pytest.mark.parametrize(
    ("entity_prefix", "digits"),
    [("&#", "9" * 5_000), ("&#x", "f" * 5_000)],
    ids=["decimal", "hexadecimal"],
)
def test_oversized_numeric_entities_remain_literal(entity_prefix: str, digits: str) -> None:
    entity = f"{entity_prefix}{digits};"
    try:
        tokens = _link_tokens(f"[x](#{entity})")
    except ValueError as error:
        pytest.fail(f"oversized numeric entity raised {error!r}")

    assert len(tokens) == 1
    assert tokens[0].fragment_target == entity


@pytest.mark.parametrize(
    ("entity", "expected"),
    [("&#0000065;", "A"), ("&#x000041;", "A")],
    ids=["decimal-seven-digit-boundary", "hex-six-digit-boundary"],
)
def test_numeric_entities_decode_at_commonmark_digit_limits(
    entity: str,
    expected: str,
) -> None:
    assert _link_tokens(f"[x](#{entity})")[0].fragment_target == expected


def test_failed_link_bodies_bound_character_work_and_keep_later_links() -> None:
    source = _CharacterWorkText("[](" * 2_048 + "[live](#live)")

    tokens = markdown_module.markdown_reference_snapshot(source).links

    assert [token.fragment_target for token in tokens] == ["live"]
    assert source.character_work <= 200 * len(source)


def test_failed_enclosing_labels_do_not_copy_children_per_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    count = 512
    source = "[" * count + "[x](#target)" * count + "]" * count
    _CopyCountingList.copied_items = 0
    monkeypatch.setattr(markdown_module, "list", _CopyCountingList, raising=False)

    tokens = markdown_module.markdown_reference_snapshot(source).links

    assert len(tokens) == count
    assert _CopyCountingList.copied_items <= 2 * count


def test_nested_link_candidates_bound_child_summary_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    count = 512
    source = "[" * count + "[x](#inner)" * count + "](#outer)" * count
    original_make_link_token = markdown_module._make_link_token
    child_work = 0

    def counted_make_link_token(
        text: str,
        token_start: int,
        end: int,
        destination_start: int,
        destination_end: int,
        is_image: bool,
        child_values: Iterable[tuple[int, int]],
    ) -> markdown_module.MarkdownLinkToken:
        nonlocal child_work
        materialized = tuple(child_values)
        child_work += len(materialized)
        return original_make_link_token(
            text,
            token_start,
            end,
            destination_start,
            destination_end,
            is_image,
            materialized,
        )

    monkeypatch.setattr(markdown_module, "_make_link_token", counted_make_link_token)

    tokens = markdown_module.markdown_reference_snapshot(source).links

    assert len(tokens) == count
    assert child_work <= 2 * count


def test_link_destination_parenthesis_nesting_limit() -> None:
    supported = "[x](#" + "(" * 32 + "target" + ")" * 32 + ")"
    unsupported = "[x](#" + "(" * 33 + "target" + ")" * 33 + ")"

    assert len(_link_tokens(supported)) == 1
    assert _link_tokens(unsupported) == ()


def test_anchor_attachment_consumes_occupied_ranges_monotonically() -> None:
    parts: list[str] = []
    ranges: list[tuple[int, int]] = []
    offset = 0
    for index in range(256):
        anchor = f"(target-{index})=\n"
        fence = "```{note}\nbody\n```\n"
        parts.extend((anchor, fence))
        fence_start = offset + len(anchor)
        ranges.append((fence_start, fence_start + len(fence)))
        offset += len(anchor) + len(fence)
    source = "".join(parts)
    tracked_ranges = _RangeWork(tuple(ranges))

    labels = markdown_module._attached_markdown_target_labels_from_opaque(
        source,
        tracked_ranges,
        frozenset(start for start, _end in ranges),
    )

    assert len(labels) == 256
    assert tracked_ranges.item_reads <= 3 * len(tracked_ranges)


def test_ordered_range_membership_bounds_item_reads() -> None:
    ranges = _RangeWork(tuple((index * 2, index * 2 + 1) for index in range(2_048)))
    query_count = 2 * len(ranges)

    for position in range(query_count):
        assert markdown_module.range_contains(position, ranges) is (position % 2 == 0)

    assert ranges.item_reads <= 16 * query_count


def test_missing_reference_is_warning() -> None:
    scan = _scan("See {eq}`missing`.\n")
    diagnostics = check_references(scan.labels, scan.references)
    assert [diagnostic.code for diagnostic in diagnostics] == ["REF002"]
    assert diagnostics[0].severity is Severity.WARNING
    assert diagnostics[0].message == "equation reference target not found: missing"


@pytest.mark.public_regression
def test_issue_226_code_contexts_are_inert_across_reference_and_math_paths() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("issue-226.md"),
        "``{eq}`missing` ``\n"
        "~~~text\n"
        "$$\n"
        "x=x+1\n"
        "$$\n"
        "{eq}`also-missing`\n"
        "~~~\n\n"
        "\t#Bad\n"
        "\tSee {ref}`missing`.\n"
        "\t$$\n"
        "\tx=x+1\n"
        "\t$$\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())
    snapshot = MySTFrontend().lower((document,))

    assert result.exit_code() == 0
    assert result.math_blocks_checked == 0
    assert result.diagnostics == ()
    assert snapshot.headings == ()
    assert snapshot.target_anchors == ()
    assert snapshot.generic_refs == ()
    assert snapshot.equation_refs == ()
    assert snapshot.display_math == ()


@pytest.mark.public_regression
def test_tab_indentation_continuing_a_paragraph_remains_prose() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("tab-paragraph.md"),
        "paragraph\n\t# {ref}`inside`\nSee {ref}`active`.\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())
    snapshot = MySTFrontend().lower((document,))

    assert [(reference.role_kind, reference.target) for reference in snapshot.generic_refs] == [
        ("ref", "inside"),
        ("ref", "active"),
    ]
    assert snapshot.headings == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF004", "REF004"]


@pytest.mark.public_regression
def test_issue_247_math_does_not_create_generic_targets() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("issue-247.md"),
        "$$\n(fake)=\n# Fake\n{ref}`inside-math`\n$$\n\nSee {ref}`fake`.\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())
    snapshot = MySTFrontend().lower((document,))

    assert [(diagnostic.code, diagnostic.detail) for diagnostic in result.diagnostics] == [
        ("PARSE020", None),
        ("REF004", "reference text: {ref}`fake`"),
    ]
    assert snapshot.headings == ()
    assert snapshot.target_anchors == ()
    assert [(reference.role_kind, reference.target) for reference in snapshot.generic_refs] == [
        ("ref", "fake")
    ]


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


def test_myst_roles_do_not_cross_line_boundaries() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "{eq}`line\nbreak`\nSee {eq}`active`.",
        DocumentKind.MARKDOWN,
    )

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [reference.target for reference in legacy.references] == ["active"]
    assert [reference.target for reference in frontend.equation_refs] == ["active"]
    assert [issue.kind for issue in frontend.structure_syntax_issues] == ["myst-role"]


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


def test_markdown_link_tokens_reject_blank_line_and_accept_soft_wrapped_titles() -> None:
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


@pytest.mark.parametrize(
    "boundary",
    [
        "```text\nbody\n```",
        "# Heading",
        "- list item",
        "<div>\nbody\n</div>",
        "---",
    ],
    ids=["fence", "heading", "list", "html", "thematic"],
)
def test_markdown_link_titles_end_at_block_boundaries(boundary: str) -> None:
    assert _link_tokens(f'[x](#fake "title\n{boundary}\ncontinued")') == ()


def test_markdown_link_label_accepts_one_soft_line_break() -> None:
    assert [token.fragment_target for token in _link_tokens("[label\ncontinued](#target)")] == [
        "target"
    ]


@pytest.mark.parametrize(
    "boundary",
    [
        "",
        "```text\ncode\n```",
        "<div>\nbody\n</div>",
        "# Heading",
        "- list item",
        "> block quote",
        "---",
        "===",
    ],
    ids=["blank", "fence", "html", "heading", "list", "quote", "thematic", "setext"],
)
def test_markdown_link_labels_end_at_block_boundaries(boundary: str) -> None:
    source = f"[label\n{boundary}\ncontinued](#ghost)\nSee [active](#active).\n"
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        source,
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())
    graph = graph_documents([document], config=Config())

    assert [diagnostic.message for diagnostic in result.diagnostics] == [
        "equation reference target not found: active"
    ]
    assert [(node.kind, node.label) for node in graph.nodes] == [("reference", "active")]
    assert [(edge.target, edge.target_label) for edge in graph.edges] == [
        ("label:active", "active")
    ]


@pytest.mark.parametrize(
    "opaque_block",
    [
        "> ```\n> [fake](#missing)\n> ```",
        "> ~~~\n> [fake](#missing)\n> ~~~",
        "- ```\n  [fake](#missing)\n  ```",
        "- ~~~\n  [fake](#missing)\n  ~~~",
        "> <div>\n> [fake](#missing)\n> </div>",
        "- <div>\n  [fake](#missing)\n  </div>",
    ],
    ids=[
        "quote-backtick-fence",
        "quote-tilde-fence",
        "list-backtick-fence",
        "list-tilde-fence",
        "quote-html",
        "list-html",
    ],
)
def test_container_relative_fences_and_html_are_opaque(opaque_block: str) -> None:
    targets = _reference_targets(f"{opaque_block}\n\nSee [active](#active).\n")

    assert targets == (["active"], ["active"], ["active"])


def test_unclosed_quote_fence_ends_when_the_quote_path_is_exited() -> None:
    source = "> ```\n> [hidden](#hidden)\n\nSee [active](#active).\n"

    assert _reference_targets(source) == (
        ["active"],
        ["active"],
        ["active"],
    )


def test_reentered_equal_shape_quote_cannot_close_the_first_fence() -> None:
    source = (
        "> ```\n"
        "> [first-hidden](#first-hidden)\n"
        "outside\n\n"
        "> ```\n"
        "> [second-hidden](#second-hidden)\n"
        "\n"
        "See [active](#active).\n"
    )

    assert _reference_targets(source) == (
        ["active"],
        ["active"],
        ["active"],
    )


def test_sibling_list_item_cannot_close_the_first_item_fence() -> None:
    source = (
        "- ```\n"
        "  [first-hidden](#first-hidden)\n"
        "- ```\n"
        "  [second-hidden](#second-hidden)\n"
        "  ```\n"
        "See [active](#active).\n"
    )

    assert _reference_targets(source) == (
        ["active"],
        ["active"],
        ["active"],
    )


def test_nested_container_looking_lines_remain_literal_fence_body() -> None:
    source = (
        "```\n"
        "- [hidden-list](#hidden-list)\n"
        "  ```\n"
        "  > [hidden-quote](#hidden-quote)\n"
        "```\n"
        "See [active](#active).\n"
    )

    assert _reference_targets(source) == (
        ["active"],
        ["active"],
        ["active"],
    )


def test_top_level_unclosed_fence_owns_the_document_end() -> None:
    source = "```\nSee [hidden](#hidden).\n"

    assert _reference_targets(source) == ([], [], [])


@pytest.mark.parametrize(
    ("boundary", "expected_targets"),
    [
        ("--", ["active"]),
        ("= =", ["target", "active"]),
        ("* * *", ["active"]),
    ],
    ids=["short-setext", "spaced-equals-prose", "spaced-thematic"],
)
def test_setext_and_thematic_boundaries_use_distinct_grammars(
    boundary: str,
    expected_targets: list[str],
) -> None:
    source = f"[label\n{boundary}\ncontinued](#target)\nSee [active](#active).\n"

    assert _reference_targets(source) == (
        expected_targets,
        expected_targets,
        expected_targets,
    )


@pytest.mark.parametrize(
    ("middle", "expected_targets"),
    [
        ("2. item", ["target", "active"]),
        ("1. item", ["active"]),
        ("*", ["target", "active"]),
        ("2.", ["target", "active"]),
        ("². item", ["target", "active"]),
        ("１. item", ["target", "active"]),
        ("\n2. item", ["active"]),
        ("\n*", ["active"]),
    ],
    ids=[
        "ordered-two-continues",
        "ordered-one-interrupts",
        "empty-bullet-continues",
        "empty-ordered-continues",
        "superscript-digit-remains-prose",
        "fullwidth-digit-remains-prose",
        "ordered-after-blank",
        "bullet-after-blank",
    ],
)
def test_list_markers_apply_paragraph_interruption_rules(
    middle: str,
    expected_targets: list[str],
) -> None:
    source = f"[label\n{middle}\ncontinued](#target)\nSee [active](#active).\n"

    assert _reference_targets(source) == (
        expected_targets,
        expected_targets,
        expected_targets,
    )


@pytest.mark.parametrize(
    ("continuation", "expected_targets"),
    [
        ("> continued](#target)", ["target", "active"]),
        ("> - item\ncontinued](#target)", ["active"]),
    ],
    ids=["partial-lazy-continuation", "partial-real-block"],
)
def test_nested_quote_lazy_continuation_preserves_the_container_path(
    continuation: str,
    expected_targets: list[str],
) -> None:
    source = f">>> [label\n{continuation}\nSee [active](#active).\n"

    assert _reference_targets(source) == (
        expected_targets,
        expected_targets,
        expected_targets,
    )


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


def test_link_metadata_is_opaque_to_math_while_visible_labels_remain_live() -> None:
    valid = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        '[$label$](https://example.invalid/$destination$ "$title$")\n'
        "![alt $image$](image.png)\n"
        "$outside$\n",
        DocumentKind.MARKDOWN,
    )
    invalid = SourceDocument.from_text(
        PurePosixPath("invalid.md"),
        "[site](#dest\n\n$$\nlive = live\n$$\n)",
        DocumentKind.MARKDOWN,
    )
    config = Config(scanner=ScannerConfig(inline_math=True))

    valid_legacy = MarkdownScanner().scan(valid, config)
    valid_frontend = MySTFrontend().lower((valid,))
    invalid_legacy = MarkdownScanner().scan(invalid, config)
    invalid_frontend = MySTFrontend().lower((invalid,))

    assert [block.text for block in valid_legacy.blocks] == ["label", "outside"]
    assert [fact.body for fact in valid_frontend.inline_math] == ["label", "outside"]
    assert valid_frontend.display_math == ()
    assert [block.text for block in invalid_legacy.blocks] == ["live = live"]
    assert [fact.body for fact in invalid_frontend.display_math] == ["live = live"]


@pytest.mark.parametrize(
    ("boundary", "headings", "fence_count", "targets"),
    [
        ("```{note}\n[hidden](#hidden)\n```", (), 1, ("active",)),
        ("# Visible", ("Visible",), 0, ("active",)),
        ("- See [inside](#inside).", (), 0, ("inside", "active")),
    ],
    ids=["fence", "heading", "list"],
)
def test_block_interrupted_link_titles_do_not_hide_structure_or_references(
    boundary: str,
    headings: tuple[str, ...],
    fence_count: int,
    targets: tuple[str, ...],
) -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        f'[site](#fake "title\n{boundary}\ncontinued")\nSee [active](#active).\n',
        DocumentKind.MARKDOWN,
    )

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [reference.target for reference in legacy.references] == list(targets)
    assert [reference.target for reference in frontend.generic_refs] == list(targets)
    assert [heading.text for heading in frontend.headings] == list(headings)
    assert len(frontend.fences) == fence_count


def test_link_like_code_cannot_claim_later_lexical_content() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        '`[x](#target` " ` {eq}`hidden` `")\nSee {eq}`active`.\n',
        DocumentKind.MARKDOWN,
    )

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [(reference.source.value, reference.target) for reference in legacy.references] == [
        ("myst_eq_role", "active")
    ]
    assert [(reference.ref_kind, reference.target) for reference in frontend.equation_refs] == [
        ("eq", "active")
    ]
    assert frontend.generic_refs == ()


def test_unmatched_nested_link_frames_preserve_source_order() -> None:
    text = "[outer [unmatched [before](#before) [inner [later](#later)"
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    tokens = _link_tokens(text)
    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [token.fragment_target for token in tokens] == ["before", "later"]
    assert [reference.target for reference in legacy.references] == ["before", "later"]
    assert [reference.target for reference in frontend.generic_refs] == ["before", "later"]


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
    assert snapshot.structure_syntax_issues == ()
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
    assert markdown_module.markdown_reference_snapshot("![alt](#target)").link_metadata_ranges == (
        (0, 15),
    )
    assert markdown_module.markdown_reference_snapshot("[x](#target)").link_metadata_ranges == (
        (4, 12),
    )

    nested = _link_tokens("[outer [inner](#inner)](#outer)")
    assert len(nested) == 1
    assert nested[0].fragment_target == "inner"

    code = markdown_module.markdown_reference_snapshot(
        "``[x](#hidden)`` and [x](#live)"
    ).opaque_ranges
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


@pytest.mark.parametrize(
    "text",
    [
        "(hidden)=\n<!--\n# Hidden\n-->\n\nSee [](#hidden).\n",
        "See [](#orphan).\n\n(orphan)=\n<!-- trailing comment -->\n",
    ],
    ids=["heading-inside-comment", "comment-only-tail"],
)
def test_opaque_or_absent_structure_does_not_attach_myst_anchor(text: str) -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        text,
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]


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


@pytest.mark.parametrize(
    ("case", "source", "live_targets"),
    [
        pytest.param(
            "four-space-block-boundary",
            "before\n\n    [hidden](#hidden)\nSee [active](#active).\n",
            ("active",),
            id="four-space",
        ),
        pytest.param(
            "tab-block-boundary",
            "before\n\n\t[hidden](#hidden)\nSee [active](#active).\n",
            ("active",),
            id="tab",
        ),
        pytest.param(
            "blank-separated-chunks",
            "before\n\n    [hidden-a](#hidden-a)\n\n    [hidden-b](#hidden-b)\n"
            "See [active](#active).\n",
            ("active",),
            id="blank-chunks",
        ),
        (
            "paragraph-continuation",
            "paragraph\n    [live](#live)\nSee [active](#active).\n",
            ("live", "active"),
        ),
        (
            "list-item-continuation",
            "- item\n\n    [live](#live)\nSee [active](#active).\n",
            ("live", "active"),
        ),
        pytest.param(
            "list-relative-code",
            "- item\n\n        [hidden](#hidden)\nSee [active](#active).\n",
            ("active",),
            id="list-code",
        ),
        pytest.param(
            "list-marker-relative-code",
            "-     [hidden](#hidden)\nSee [active](#active).\n",
            ("active",),
            id="list-marker-code",
        ),
        pytest.param(
            "tab-list-marker-relative-code",
            "-\t\t[hidden](#hidden)\nSee [active](#active).\n",
            ("active",),
            id="tab-list-marker-code",
        ),
        pytest.param(
            "wide-list-continuation",
            "100. item\n\n        [live](#live)\nSee [active](#active).\n",
            ("live", "active"),
            id="wide-list-prose",
        ),
        pytest.param(
            "wide-list-relative-code",
            "100. item\n\n         [hidden](#hidden)\nSee [active](#active).\n",
            ("active",),
            id="wide-list-code",
        ),
        pytest.param(
            "tab-list-relative-code",
            "- item\n\n\t\t[hidden](#hidden)\nSee [active](#active).\n",
            ("active",),
            id="tab-list-code",
        ),
        pytest.param(
            "nested-block-quote",
            "> quote\n\n>     [hidden](#hidden)\nSee [active](#active).\n",
            ("active",),
            id="block-quote",
        ),
        pytest.param(
            "nested-quote-list-code",
            "> > - item\n> >\n> >         [hidden](#hidden)\nSee [active](#active).\n",
            ("active",),
            id="nested-quote-list-code",
        ),
        pytest.param(
            "lazy-quote-continuation",
            "> > paragraph\n    [live](#live)\nSee [active](#active).\n",
            ("live", "active"),
            id="lazy-quote-prose",
        ),
    ],
)
def test_indented_code_does_not_create_reference_facts(
    case: str,
    source: str,
    live_targets: tuple[str, ...],
) -> None:
    document = SourceDocument.from_text(
        PurePosixPath(f"{case}.md"),
        source,
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())
    graph = graph_documents([document], config=Config())

    def line_col(index: int, *, end: bool = False) -> tuple[int, int]:
        if end:
            index = max(0, index - 1)
        line_start = source.rfind("\n", 0, index) + 1
        return source.count("\n", 0, index) + 1, index - line_start + 1

    expected_diagnostics: list[Diagnostic] = []
    expected_nodes: list[tuple[object, ...]] = []
    expected_edges: list[tuple[object, ...]] = []
    path = PurePosixPath(f"{case}.md")
    for target in live_targets:
        raw = f"[{target}](#{target})"
        link_start = source.index(raw)
        target_start = link_start + raw.index(f"#{target}") + 1
        target_end = target_start + len(target)
        target_line, target_col = line_col(target_start)
        target_end_line, target_end_col = line_col(target_end, end=True)
        expected_diagnostics.append(
            Diagnostic(
                code="REF002",
                severity=Severity.WARNING,
                message=f"equation reference target not found: {target}",
                span=SourceSpan(
                    path=path,
                    start=target_start,
                    end=target_end,
                    line=target_line,
                    col=target_col,
                    end_line=target_end_line,
                    end_col=target_end_col,
                ),
                detail=f"reference text: {raw}",
                rule="references",
            )
        )
        expected_nodes.append(
            (
                f"ref:{path.as_posix()}:{target_start}",
                "reference",
                target,
                "markdown_anchor",
                path,
                target_line,
                target_col,
                target_end_line,
                target_end_col,
            )
        )
        expected_edges.append(
            (
                f"ref:{path.as_posix()}:{target_start}",
                f"label:{target}",
                "references",
                target,
                raw,
                "markdown_anchor",
            )
        )

    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert result.config_path is None
    assert result.exit_code() == 0
    assert result.diagnostics == tuple(expected_diagnostics)
    assert graph.schema_version == "0.3"
    assert [
        (
            node.id,
            node.kind,
            node.label,
            node.source,
            node.span.path,
            node.span.line,
            node.span.col,
            node.span.end_line,
            node.span.end_col,
        )
        for node in graph.nodes
    ] == expected_nodes
    assert [
        (edge.source, edge.target, edge.kind, edge.target_label, edge.raw, edge.source_kind)
        for edge in graph.edges
    ] == expected_edges


def test_only_active_empty_myst_role_is_malformed_syntax() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("lecture.md"),
        '\\{ref}`   `\n[x](https://example.invalid/ "{eq}`   `")\n{ref}`   `\n',
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["DIR011"]


def test_reference_fixture_covers_tokenized_contexts() -> None:
    path = Path("tests/fixtures/good/references_good.md")
    document = SourceDocument.from_text(
        PurePosixPath(path.as_posix()),
        path.read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert result.diagnostics == ()
