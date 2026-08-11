from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from scieqlint import markdown as markdown_module
from scieqlint.api import check_documents
from scieqlint.config.model import ChecksConfig, Config, ScannerConfig, SymbolsConfig
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.markdown import (
    code_fence_ranges,
    inline_code_ranges,
    markdown_reference_snapshot,
)
from scieqlint.scan import markdown as markdown_scan_module
from scieqlint.scan.base import (
    MathContainer,
    ReferenceSource,
    SymbolDirectiveSource,
)
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


class _RegexTraversal:
    def __init__(self, pattern, work: list[int]) -> None:
        self._pattern = pattern
        self._work = work

    def finditer(self, string: str, pos: int = 0, endpos: int | None = None):
        search_end = len(string) if endpos is None else endpos
        self._work[0] += search_end - pos
        return self._pattern.finditer(string, pos, search_end)

    def search(self, string: str, pos: int = 0, endpos: int | None = None):
        search_end = len(string) if endpos is None else endpos
        match = self._pattern.search(string, pos, search_end)
        self._work[0] += (match.end() if match is not None else search_end) - pos
        return match


@pytest.mark.parametrize(
    "source",
    [
        "\\" * 2_048,
        "x$$" * 1_024 + "\n",
        "$$\n" + "x$$" * 1_024 + "\n$$\n",
    ],
    ids=["backslash-run", "rejected-openers", "candidate-closers"],
)
def test_ordered_markdown_lexer_bounds_explicit_character_work(source: str) -> None:
    tracked = _CharacterWorkText(source)

    markdown_reference_snapshot(tracked)

    assert tracked.character_work <= 20 * len(tracked)


def test_repeated_unclosed_html_blocks_bound_regex_traversal(monkeypatch) -> None:
    source = "<div>\n\n" * 512
    regex_work = [0]
    original_compile = markdown_module.re.compile

    tag_events = getattr(markdown_module, "HTML_TAG_EVENT_RE", None)
    if tag_events is not None:
        monkeypatch.setattr(
            markdown_module,
            "HTML_TAG_EVENT_RE",
            _RegexTraversal(tag_events, regex_work),
        )
    monkeypatch.setattr(
        markdown_module.re,
        "compile",
        lambda pattern, flags=0: _RegexTraversal(original_compile(pattern, flags), regex_work),
    )

    ranges = markdown_opaque_ranges(source)

    assert len(ranges) == 512
    assert regex_work[0] <= 2 * len(source)


def test_scanner_display_diagnostics_bound_closed_range_work(monkeypatch) -> None:
    block_count = 512
    source = "$$\nx = x\n$$\n" * block_count
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        source,
        DocumentKind.MARKDOWN,
    )
    any_work = [0]
    original_any = any

    def counting_any(iterable):
        def counted():
            for value in iterable:
                any_work[0] += 1
                yield value

        return original_any(counted())

    monkeypatch.setattr(markdown_scan_module, "any", counting_any, raising=False)

    result = MarkdownScanner().scan(document, Config())

    assert len(result.blocks) == block_count
    assert result.diagnostics == ()
    assert any_work[0] <= 8 * len(source)


def test_scans_display_math_label_and_markdown_reference() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\nE = m c^2\n$$ {#eq-energy}\n\nSee [Eq.](#eq-energy).\n",
        DocumentKind.MARKDOWN,
    )
    result = MarkdownScanner().scan(document, Config())
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert block.container is MathContainer.MARKDOWN_DISPLAY
    assert block.span.line == 2
    assert block.source_aligned_text == block.text
    assert document.text[block.span.start : block.span.end] == block.source_aligned_text
    assert [label.label for label in result.labels] == ["eq-energy"]
    assert [(ref.target, ref.source) for ref in result.references] == [
        ("eq-energy", ReferenceSource.MARKDOWN_ANCHOR),
    ]


def test_inline_math_scans_only_when_enabled() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Inline $(a+b)^2 = a^2 + b^2$ example.\n",
        DocumentKind.MARKDOWN,
    )
    assert MarkdownScanner().scan(document, Config()).blocks == ()

    config = Config(scanner=ScannerConfig(inline_math=True))
    result = MarkdownScanner().scan(document, config)

    assert len(result.blocks) == 1
    assert result.blocks[0].container is MathContainer.MARKDOWN_INLINE


def test_inline_dollar_math_span_tracks_trimmed_source_body() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $  x = y  $.\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    block = result.blocks[0]
    assert block.text == "x = y"
    assert block.source_aligned_text == block.text
    assert block.span.col == 9
    assert document.text[block.span.start : block.span.end] == block.source_aligned_text


def test_inline_dollar_math_span_preserves_tabs_and_combining_unicode() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $\t x\u0301 = y \t $.\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    block = result.blocks[0]
    assert block.text == "x\u0301 = y"
    assert block.source_aligned_text == block.text
    assert document.text[block.span.start : block.span.end] == block.source_aligned_text


def test_inline_dollar_math_whitespace_only_body_is_not_a_fact() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $ \t $ after.\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert result.blocks == ()
    assert result.diagnostics == ()


def test_inline_dollar_math_symbol_diagnostics_use_trimmed_source_columns() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $  x = y  $.\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents(
        [document],
        config=Config(
            scanner=ScannerConfig(inline_math=True),
            checks=ChecksConfig(symbols=SymbolsConfig(enabled=True)),
        ),
    )

    assert [
        (diagnostic.code, diagnostic.detail, diagnostic.span.col)
        for diagnostic in result.diagnostics
        if diagnostic.span is not None
    ] == [("SYM001", "x", 9), ("SYM001", "y", 13)]


def test_inline_math_ignores_code_spans_and_non_math_fences() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        'Code span `$not = math$`.\n\n```python\nalso = "$not_math$"\n```\n',
        DocumentKind.MARKDOWN,
    )
    config = Config(scanner=ScannerConfig(inline_math=True))

    result = MarkdownScanner().scan(document, config)

    assert result.blocks == ()


def test_fence_transition_does_not_pair_backticks_across_live_math() -> None:
    text = "```python\ncode\n````\n$x=x+1$\n```\n"
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    assert inline_code_ranges(text) == ()
    assert (
        MarkdownScanner()
        .scan(
            document,
            Config(scanner=ScannerConfig(inline_math=True)),
        )
        .blocks[0]
        .text
        == "x=x+1"
    )
    assert [fact.body for fact in MySTFrontend().lower((document,)).inline_math] == ["x=x+1"]


def test_tilde_fence_transition_does_not_pair_backticks_across_live_math() -> None:
    text = "~~~python\n`\n~~~\n$x=x+1$\n`\n"
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    assert inline_code_ranges(text) == ()
    assert (
        MarkdownScanner()
        .scan(
            document,
            Config(scanner=ScannerConfig(inline_math=True)),
        )
        .blocks[0]
        .text
        == "x=x+1"
    )
    assert [fact.body for fact in MySTFrontend().lower((document,)).inline_math] == ["x=x+1"]


def test_dollar_math_does_not_pair_across_raw_html() -> None:
    text = "<div>\n$$\n</div>\n$$\n"
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        text,
        DocumentKind.MARKDOWN,
    )

    assert MarkdownScanner().scan(document, Config()).blocks == ()
    assert MySTFrontend().lower((document,)).display_math == ()


def test_empty_and_plain_markdown_have_no_code_ranges() -> None:
    assert inline_code_ranges("") == ()
    assert inline_code_ranges("plain text") == ()


def test_unterminated_display_math_emits_scan_warning() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\na = a\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]
    assert result.diagnostics[0].span.line == 1
    assert result.diagnostics[0].rule == "scanner"


def test_unterminated_inline_math_does_not_hide_the_next_line() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$x\n$y$\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert [block.text for block in result.blocks] == ["y"]
    assert result.diagnostics == ()


def test_unterminated_display_without_a_final_newline_warns() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\nx = x",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]


def test_closed_display_math_does_not_emit_scan_warning() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\na = a\n$$\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert len(result.blocks) == 1
    assert result.diagnostics == ()


def test_dollar_math_respects_escape_and_block_boundaries() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        r"Literal \$x=x+1$." + "\n" + "Prose $$x=x+1$$ tail.\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert result.blocks == ()
    assert result.diagnostics == ()


def test_display_dollar_math_requires_a_line_boundary_and_allows_indent() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "  $$\nx = x\n  $$\n\nprose $$y = y$$\n\n$$$z = z$$$\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [block.text for block in result.blocks] == ["x = x"]
    assert result.diagnostics == ()


def test_inline_dollar_math_allows_text_boundaries() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "word$x = x$ and $x = x$word\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert [block.text for block in result.blocks] == ["x = x", "x = x"]
    assert result.diagnostics == ()


def test_inline_dollar_math_skips_escaped_closers_and_keeps_even_slashes_active() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        r"$x=\$3=x$ and \\$y$.",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert [block.text for block in result.blocks] == [r"x=\$3=x", "y"]


def test_dollar_tail_accepts_only_a_complete_label_suffix() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\nx = x\n$$ prose (ghost)\nmore\n$$ {#real}\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [label.label for label in result.labels] == ["real"]


def test_display_dollar_math_skips_invalid_candidate_closers() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\nx = x\n$$ (bad label)\n\\$$\n$$$\n$$\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [block.text for block in result.blocks] == ["x = x\n$$ (bad label)\n\\$$\n$$$"]
    assert result.diagnostics == ()


def test_escaped_myst_role_keeps_following_math_active() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "\\{ref}`target` and $x$\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert [block.text for block in result.blocks] == ["x"]
    assert result.diagnostics == ()


def test_display_delimiter_in_inline_code_does_not_emit_scan_warning() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Use `$$` and ``$$`` literally.\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert result.diagnostics == ()


def test_display_delimiter_in_non_math_fence_does_not_emit_scan_warning() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        '```python\nprint("$$")\n```\n',
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert result.diagnostics == ()


def test_display_math_does_not_close_when_dollars_have_trailing_backtick_text() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\na = a\n`$$`\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]


def test_legacy_and_frontend_share_source_order_for_math_and_backticks() -> None:
    text = "$$\nleft\n`$$`\nright\ntext\n$$\noutside\n$$\noutside\n$$\n"
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [block.text for block in legacy.blocks] == ["left\n`$$`\nright\ntext", "outside"]
    assert [math.body for math in frontend.display_math] == [
        "left\n`$$`\nright\ntext",
        "outside",
    ]
    assert frontend.display_math[0].span is not None
    assert (legacy.blocks[0].span.start, legacy.blocks[0].span.end) == (
        frontend.display_math[0].span.start,
        frontend.display_math[0].span.end,
    )
    assert legacy.diagnostics == ()


def test_shared_fence_closer_rules_keep_adjacent_math_fences_distinct() -> None:
    text = "```math\nfirst = first\n````\n```math\nsecond = second\n```\n"
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [block.text for block in legacy.blocks] == ["first = first", "second = second"]
    assert [fence.info_string for fence in frontend.fences] == ["math", "math"]
    assert legacy.diagnostics == ()


@pytest.mark.parametrize(
    ("opener", "closer", "expected"),
    [
        ("```math", "```", True),
        ("```{math}", "```", True),
        (" ```math", "```", False),
        (" ```{math}", "```", False),
        ("````math", "````", False),
        ("````{math}", "````", False),
    ],
)
def test_legacy_math_fence_opener_profile(opener: str, closer: str, expected: bool) -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        f"{opener}\nx = x\n{closer}\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [block.text for block in result.blocks] == (["x = x"] if expected else [])
    assert result.diagnostics == ()


def test_unclosed_display_suppresses_nested_math_fence_diagnostic() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\n```math\nhidden = hidden\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]


def test_legacy_and_frontend_display_math_ignore_tilde_fence_delimiters() -> None:
    text = "~~~\n$$\ninside = inside\n$$\n~~~\n\n$$\noutside = outside\n$$\n"
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert [block.text for block in legacy.blocks] == ["outside = outside"]
    assert [math.body for math in frontend.display_math] == ["outside = outside"]
    assert frontend.display_math[0].span is not None
    assert (legacy.blocks[0].span.start, legacy.blocks[0].span.end) == (
        frontend.display_math[0].span.start,
        frontend.display_math[0].span.end,
    )
    assert legacy.diagnostics == ()


def test_legacy_and_frontend_display_math_ignore_unclosed_tilde_fences() -> None:
    text = "~~~\n$$\ninside = inside\n$$\n"
    document = SourceDocument.from_text(PurePosixPath("paper.md"), text, DocumentKind.MARKDOWN)

    legacy = MarkdownScanner().scan(document, Config())
    frontend = MySTFrontend().lower((document,))

    assert legacy.blocks == ()
    assert frontend.display_math == ()
    assert legacy.diagnostics == ()


def test_display_math_does_not_close_when_dollars_have_trailing_multibacktick_text() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\na = a\n``$$``\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.blocks == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]


def test_escaped_backticks_do_not_open_code_spans_but_even_slashes_do() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "\\`$x$ and \\\\`$y$`\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert [block.text for block in result.blocks] == ["x"]
    assert result.diagnostics == ()


def test_inline_html_tags_leave_inline_content_live() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<span>$x$</span> and \\<span>$y$</span>\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert [block.text for block in result.blocks] == ["x", "y"]
    assert result.diagnostics == ()


def test_nested_block_html_keeps_math_content_opaque_until_the_matching_close() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "  <div>\n"
        "<div>\n"
        "$x$\n"
        "</div>\n"
        "$z$\n"
        "</div>\n\n"
        "$y$\n\n"
        "(visible)=\n"
        "# Visible\n"
        "```python\n"
        "pass\n"
        "```\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert [block.text for block in result.blocks] == ["y"]
    assert result.diagnostics == ()
    snapshot = MySTFrontend().lower((document,))
    assert [fact.body for fact in snapshot.inline_math] == ["y"]
    assert [heading.text for heading in snapshot.headings] == ["Visible"]
    assert [anchor.label for anchor in snapshot.target_anchors] == ["visible"]
    assert [fence.language for fence in snapshot.fences] == ["python"]


def test_unclosed_block_html_ends_at_a_blank_line() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<div>\n$x$\n\n$y$\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert [block.text for block in result.blocks] == ["y"]
    assert result.diagnostics == ()


def test_unclosed_rawtext_html_keeps_math_content_opaque() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<script>\n$x$",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert result.blocks == ()
    assert result.diagnostics == ()


@pytest.mark.parametrize(
    "source",
    [
        "</script>\n<script>\n$x$\n</script>\n$y$\n",
        "</div>\n<div/>\n$x$\n</div>\n$y$\n",
        "<span>\n<div>\n$x$\n</div>\n$y$\n",
    ],
    ids=["earlier-raw-close", "self-closing-block", "unrelated-tag"],
)
def test_html_block_close_index_preserves_edge_semantics(source: str) -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        source,
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert [block.text for block in result.blocks] == ["y"]
    assert result.diagnostics == ()


def test_inline_math_stays_opaque_inside_a_longer_backtick_span() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "``$x$ `inner` tail``\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert result.blocks == ()
    assert result.diagnostics == ()
    assert MySTFrontend().lower((document,)).inline_math == ()


def test_math_opened_before_backticks_owns_the_first_dollar_closer() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$a `x$ z` tail$\n",
        DocumentKind.MARKDOWN,
    )

    legacy = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )
    frontend = MySTFrontend().lower((document,))

    assert [block.text for block in legacy.blocks] == ["a `x"]
    assert [math.body for math in frontend.inline_math] == ["a `x"]
    assert legacy.diagnostics == ()


def test_inline_math_stays_opaque_inside_a_multiline_backtick_span() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Use ``foo\n$x$\nbar`` end.\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(
        document,
        Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert result.blocks == ()
    assert result.diagnostics == ()


def test_fence_closer_allows_at_most_three_leading_spaces() -> None:
    for spaces in range(4):
        text = f"```\ninside\n{' ' * spaces}```\noutside\n"
        close_start = text.index("```", text.index("inside") + len("inside"))
        assert code_fence_ranges(text) == ((0, close_start + 4),)

    text = "```\ninside\n  ``` \t\noutside\n"
    assert code_fence_ranges(text) == ((0, text.index("outside")),)

    text = "```\ninside\n    ```\noutside\n```\n"
    assert code_fence_ranges(text) == ((0, len(text)),)


def test_fence_closer_requires_the_marker_type_and_length() -> None:
    text = "````\ninside\n```\n~~~\n`````\noutside\n"

    close_start = text.index("`````")
    assert code_fence_ranges(text) == ((0, close_start + 6),)


def test_backtick_fence_info_string_cannot_contain_a_backtick() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "```info`\n$$\nx = x\n$$\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [block.text for block in result.blocks] == ["x = x"]
    assert result.diagnostics == ()


def test_markdown_symbol_directive_fixture_is_extracted() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("tests/fixtures/good/symbol_directives.md"),
        Path("tests/fixtures/good/symbol_directives.md").read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [
        (directive.symbol, directive.description, directive.dimension)
        for directive in result.symbol_directives
    ] == [("E", "energy", "M L^2 T^-2")]
    assert result.symbol_directives[0].source is SymbolDirectiveSource.MARKDOWN_COMMENT
    span = result.symbol_directives[0].span
    assert document.text[span.start : span.end] == "E"
    assert result.diagnostics == ()


def test_markdown_lexical_precedence_fixture_keeps_only_live_display_math() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("tests/fixtures/good/markdown_lexical_precedence.md"),
        Path("tests/fixtures/good/markdown_lexical_precedence.md").read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [block.text for block in result.blocks] == ["E = m c^2"]
    assert result.diagnostics == ()


@pytest.mark.public_regression
def test_public_escaped_tex_label_in_markdown_math_is_not_an_equation_label() -> None:
    source = (
        "$$\ny = y\n\\label{live}\n\\\\label{escaped}\n$$\n\nSee {eq}`live` and {eq}`escaped`.\n"
    )
    document = SourceDocument.from_text(PurePosixPath("paper.md"), source, DocumentKind.MARKDOWN)

    result = check_documents([document], config=Config())

    assert result.math_blocks_checked == 1
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]
    span = result.diagnostics[0].span
    assert span is not None
    assert source[span.start : span.end] == "escaped"


def test_malformed_markdown_symbol_directive_warns_and_code_fence_is_ignored() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("tests/fixtures/bad/symbol_directives_bad.md"),
        Path("tests/fixtures/bad/symbol_directives_bad.md").read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert result.symbol_directives == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN010"]


def test_markdown_symbol_directive_dimension_is_optional() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<!-- scieqlint-symbol: n = sample count -->\n",
        DocumentKind.MARKDOWN,
    )

    result = MarkdownScanner().scan(document, Config())

    assert [
        (directive.symbol, directive.description, directive.dimension)
        for directive in result.symbol_directives
    ] == [("n", "sample count", None)]
