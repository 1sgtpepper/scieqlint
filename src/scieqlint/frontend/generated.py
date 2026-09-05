"""Generated-formula source facts for conservative Markdown input."""

from __future__ import annotations

import re
from collections.abc import Sequence

from scieqlint.facts.generated import (
    GeneratedBracketDelimiter,
    GeneratedFormulaFact,
    GeneratedPlaceholderKind,
)
from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.io.source import SourceDocument
from scieqlint.markdown import (
    MarkdownLinkToken,
    _markdown_line_ownership_for_generated,  # pyright: ignore[reportPrivateUsage]
    is_escaped,
    without_tex_comments,
)
from scieqlint.source.maps import SourceMap

from .myst_shared import MYST_OPTION_RE, OffsetRange, in_ranges, line_ranges

# Semantic classification is owned by MathHost after candidate extraction.

_LATEX_ATOM_RE = re.compile(r"[A-Za-z]+")
_FORMULA_MARKER = "formula-not-decoded"
_FORMULA_MARKER_LINE_RE = re.compile(
    r"(?:formula-not-decoded|\[formula-not-decoded\]|<!--\s*formula-not-decoded\s*-->)"
)
_FORMULA_IMAGE_ALT_RE = re.compile(
    r"(?:formula|equation|math)[ _-]+"
    r"(?:placeholder|not[ _-]*decoded|image[ _-]*(?:placeholder|not[ _-]*decoded))",
    re.IGNORECASE,
)
_FORMULA_IMAGE_NAME_RE = re.compile(
    r"(?:formula|equation|math)[_-](?:placeholder|not[_-]*decoded)"
    r"(?:[_-][A-Za-z0-9]+)*"
    r"\.(?:avif|gif|jpe?g|png|svg|webp)",
    re.IGNORECASE,
)


def scan_formula_candidates(
    document: SourceDocument,
    inline_math: Sequence[InlineMathFact],
    display_math: Sequence[DisplayMathFact],
) -> tuple[GeneratedFormulaFact, ...]:
    """Emit one source-spanned candidate for each explicit math container."""

    source_math: tuple[InlineMathFact | DisplayMathFact, ...] = (
        *display_math,
        *(fact for fact in inline_math if fact.delimiter_kind != "plain-text"),
    )
    facts: list[GeneratedFormulaFact] = []
    for math_fact in source_math:
        assert math_fact.document_id == document.path.as_posix()
        assert math_fact.span is not None
        segment = document.text[math_fact.span.start : math_fact.span.end]
        text = segment
        if isinstance(math_fact, DisplayMathFact) and math_fact.option_prefix_length:
            prefix = math_fact.option_prefix_length
            # Options are opaque, but masking must preserve source locations.
            text = (
                "".join(char if char in "\r\n" else " " for char in segment[:prefix])
                + segment[prefix:]
            )
        facts.append(
            GeneratedFormulaFact(
                fact_id=(
                    f"{document.path.as_posix()}::generated-formula::candidate::"
                    f"{math_fact.span.start}"
                ),
                document_id=document.path.as_posix(),
                span=math_fact.span,
                raw=segment,
                confidence="source",
                kind="candidate",
                text=text,
                candidate_kind="formula-text",
                source_math_fact_id=math_fact.fact_id,
            )
        )
    return tuple(
        sorted(
            facts,
            key=lambda fact: (fact.span.start if fact.span is not None else -1, fact.fact_id),
        )
    )


def scan_bracketed_latex_blocks(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
) -> tuple[GeneratedFormulaFact, ...]:
    """Record standalone generated LaTeX blocks outside owned containers."""

    facts: list[GeneratedFormulaFact] = []
    occupied = _merge_ranges(tuple(item for item in occupied if item[0] != item[1]))
    opener: int | None = None
    opener_container: tuple[int, ...] | None = None
    opener_kind: GeneratedBracketDelimiter | None = None
    opener_has_latex_signal = False
    closed_previous_line = False
    active_text = without_tex_comments(document.text)
    lines = line_ranges(document.text)
    ownership = _markdown_line_ownership_for_generated(document.text)
    occupied_cursor = _RangeCursor(occupied)
    for line_index, (line_start, line_end, _line) in enumerate(lines):
        recognized_close_previous_line = closed_previous_line
        closed_previous_line = False
        content_start, content, container_key, _block_start, _block_end, _text_role = ownership[
            line_index
        ]
        active_line = active_text[content_start : content_start + len(content)]
        stripped = active_line.strip(" \t")
        candidate_start = content_start + len(active_line) - len(active_line.lstrip(" \t"))
        line_is_occupied = occupied_cursor.overlaps(line_start, line_end)

        if opener is not None and (
            (line_is_occupied and "](" in active_line) or stripped.startswith("]:")
        ):
            # A multiline Markdown link owns its destination metadata, but its
            # label remains ordinary text. Reference-definition tails are likewise
            # not generated display closers.
            opener = None
            opener_container = None
            opener_kind = None
            opener_has_latex_signal = False

        if opener is not None and container_key != opener_container:
            assert opener_kind is not None
            _record_bracketed_block(
                facts,
                document,
                smap,
                opener,
                line_start,
                False,
                opener_kind,
                opener_has_latex_signal,
            )
            opener = None
            opener_container = None
            opener_kind = None
            opener_has_latex_signal = False

        if opener is not None and line_is_occupied:
            assert opener_kind is not None
            _record_bracketed_block(
                facts,
                document,
                smap,
                opener,
                line_start,
                False,
                opener_kind,
                opener_has_latex_signal,
            )
            opener = None
            opener_container = None
            opener_kind = None
            opener_has_latex_signal = False

        if (
            opener is not None
            and stripped
            and stripped not in {r"\]", "]"}
            and _is_text_item_start(ownership, line_index)
        ):
            assert opener_kind is not None
            _record_bracketed_block(
                facts,
                document,
                smap,
                opener,
                line_start,
                False,
                opener_kind,
                opener_has_latex_signal,
            )
            opener = None
            opener_container = None
            opener_kind = None
            opener_has_latex_signal = False

        if line_is_occupied:
            continue

        if opener is None:
            same_line_close = stripped.endswith(r"\]") and stripped != r"\]"
            close_start = content_start + active_line.rfind(r"\]")
            if same_line_close:
                same_line_close = not is_escaped(document.text, close_start)
            opener_is_standalone = (
                _is_text_item_start(ownership, line_index) or recognized_close_previous_line
            )
            if opener_is_standalone and stripped.startswith(r"\[") and same_line_close:
                close_offset = close_start + 2
                _record_bracketed_block(
                    facts,
                    document,
                    smap,
                    candidate_start,
                    close_offset,
                    True,
                    "escaped",
                    True,
                )
                closed_previous_line = True
            elif opener_is_standalone and stripped.startswith(r"\["):
                opener = candidate_start
                opener_container = container_key
                opener_kind = "escaped"
                opener_has_latex_signal = True
            elif opener_is_standalone and stripped == "[":
                opener = candidate_start
                opener_container = container_key
                opener_kind = "literal"
                opener_has_latex_signal = False
            continue

        assert opener_kind is not None
        if opener_kind == "literal":
            opener_has_latex_signal = opener_has_latex_signal or _contains_latex_signal(active_line)
        if stripped == (r"\]" if opener_kind == "escaped" else "]"):
            close_offset = candidate_start + (2 if opener_kind == "escaped" else 1)
            _record_bracketed_block(
                facts,
                document,
                smap,
                opener,
                close_offset,
                True,
                opener_kind,
                opener_has_latex_signal,
            )
            opener = None
            opener_container = None
            opener_kind = None
            opener_has_latex_signal = False
            closed_previous_line = True
        # A nested standalone opener remains content of the first block. This gives
        # the malformed input one deterministic owner and one EOF/close outcome.

    if opener is not None:
        assert opener_kind is not None
        _record_bracketed_block(
            facts,
            document,
            smap,
            opener,
            len(document.text),
            False,
            opener_kind,
            opener_has_latex_signal,
        )
    return tuple(facts)


def _contains_latex_signal(text: str) -> bool:
    """Recognize TeX or concise equation text without treating prose as math."""

    for index, character in enumerate(text):
        if (
            character == "\\"
            and not is_escaped(text, index)
            and index + 1 < len(text)
            and text[index + 1].isalpha()
        ):
            return True
    atoms = _LATEX_ATOM_RE.findall(text)
    return "=" in text and bool(atoms) and all(len(atom) <= 2 for atom in atoms)


def _record_bracketed_block(
    facts: list[GeneratedFormulaFact],
    document: SourceDocument,
    smap: SourceMap,
    start: int,
    end: int,
    complete: bool,
    delimiter_kind: GeneratedBracketDelimiter,
    has_latex_signal: bool,
) -> None:
    """Keep literal square wrappers quiet unless their body is TeX-looking."""

    if delimiter_kind == "literal" and not has_latex_signal:
        return
    facts.append(
        _bracketed_block_fact(
            document,
            smap,
            start,
            end,
            complete,
            delimiter_kind=delimiter_kind,
        )
    )


def _bracketed_block_fact(
    document: SourceDocument,
    smap: SourceMap,
    start: int,
    end: int,
    complete: bool,
    delimiter_kind: GeneratedBracketDelimiter,
) -> GeneratedFormulaFact:
    text = document.text[start:end]
    return GeneratedFormulaFact(
        fact_id=f"{document.path.as_posix()}::generated-formula::bracketed-block::{start}",
        document_id=document.path.as_posix(),
        span=smap.span(start, end),
        raw=text,
        confidence="source",
        kind="candidate",
        text=text,
        candidate_kind="bracketed-block",
        complete=complete,
        delimiter_kind=delimiter_kind,
    )


def _merge_ranges(ranges: Sequence[OffsetRange]) -> tuple[OffsetRange, ...]:
    merged: list[OffsetRange] = []
    for start, end in sorted(ranges):
        assert start < end
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return tuple(merged)


def _is_text_item_start(
    line_ownership: Sequence[tuple[int, str, tuple[int, ...], bool, bool, str]],
    index: int,
) -> bool:
    _content_start, _content, container_key, block_start, _block_end, _text_role = line_ownership[
        index
    ]
    if block_start or index == 0:
        return True
    (
        _previous_start,
        previous_content,
        previous_key,
        _previous_block_start,
        previous_block_end,
        _previous_text_role,
    ) = line_ownership[index - 1]
    return previous_key != container_key or previous_block_end or not previous_content.strip(" \t")


class _RangeCursor:
    """Sweep ordered ranges once for source-ordered overlap queries."""

    def __init__(self, ranges: Sequence[OffsetRange]) -> None:
        self._ranges = ranges
        self._index = 0

    def overlaps(self, start: int, end: int) -> bool:
        while self._index < len(self._ranges) and self._ranges[self._index][1] <= start:
            self._index += 1
        if self._index >= len(self._ranges):
            return False
        range_start, _range_end = self._ranges[self._index]
        return range_start < end

    def owner_start(self, position: int) -> int | None:
        while self._index < len(self._ranges) and self._ranges[self._index][1] <= position:
            self._index += 1
        if self._index >= len(self._ranges):
            return None
        range_start, _range_end = self._ranges[self._index]
        return range_start if range_start <= position else None


def _owned_marker_comment(
    line_start: int,
    marker_start: int,
    stripped: str,
    opaque_owner: int,
    block_start: bool,
    content_start: int,
) -> bool:
    """Allow an HTML marker only when it opens the current opaque block."""

    if not stripped.startswith("<!--") or marker_start < content_start:
        return False
    if marker_start - content_start > 3:
        return False
    return opaque_owner == line_start or (block_start and marker_start == content_start)


def scan_formula_placeholders(
    document: SourceDocument,
    smap: SourceMap,
    inline_math: Sequence[InlineMathFact],
    display_math: Sequence[DisplayMathFact],
    dollar_ranges: Sequence[tuple[int, int, int, int]],
    links: Sequence[MarkdownLinkToken],
    opaque: Sequence[OffsetRange],
    code: Sequence[OffsetRange],
) -> tuple[GeneratedFormulaFact, ...]:
    """Record explicit generated formula placeholders without guessing repairs."""

    facts: list[GeneratedFormulaFact] = []
    occupied: list[OffsetRange] = []
    source_math: tuple[InlineMathFact | DisplayMathFact, ...] = (
        *display_math,
        *(fact for fact in inline_math if fact.delimiter_kind != "plain-text"),
    )
    # This scan runs before MathHost can drop non-math raw candidates, so their
    # source spans still own nested marker and image syntax.
    owned_math_ranges = _merge_ranges(
        tuple(
            (fact.span.start, fact.span.end)
            for fact in source_math
            if fact.document_id == document.path.as_posix()
            and fact.span is not None
            and fact.span.start != fact.span.end
        )
    )
    for math_fact in source_math:
        assert math_fact.document_id == document.path.as_posix()
        assert math_fact.span is not None
        source_text = document.text[math_fact.span.start : math_fact.span.end]
        active_text = _active_math_body(
            source_text,
            math_fact.container if isinstance(math_fact, DisplayMathFact) else "",
        )
        if active_text.strip() != _FORMULA_MARKER:
            continue
        marker_offset = active_text.index(_FORMULA_MARKER)
        start = math_fact.span.start + marker_offset
        facts.append(
            _placeholder_fact(
                document,
                smap,
                start,
                start + len(_FORMULA_MARKER),
                _FORMULA_MARKER,
                source_math_fact_id=math_fact.fact_id,
            )
        )
        occupied.append((math_fact.span.start, math_fact.span.end))

    for math_fact in display_math:
        if (
            math_fact.document_id != document.path.as_posix()
            or math_fact.span is None
            or math_fact.container not in {"fenced-math", "myst-math-directive"}
            or not math_fact.complete
            or _active_math_body(math_fact.body, math_fact.container).strip()
        ):
            continue
        facts.append(
            _placeholder_fact(
                document,
                smap,
                math_fact.span.start,
                math_fact.span.end,
                "empty-display-math",
                complete=True,
            )
        )
        if math_fact.span.start != math_fact.span.end:
            occupied.append((math_fact.span.start, math_fact.span.end))

    code = _merge_ranges(code)
    opaque = _merge_ranges(opaque)
    # Source-line candidates are disjoint and visited in order, so accepted
    # earlier markers cannot overlap a later line; only pre-existing ranges need
    # to be swept here.
    occupied_cursor = _RangeCursor(_merge_ranges(occupied))
    owned_math_cursor = _RangeCursor(owned_math_ranges)
    opaque_cursor = _RangeCursor(opaque)
    lines = line_ranges(document.text)
    ownership = _markdown_line_ownership_for_generated(document.text)
    for line_index, (line_start, _line_end, _line) in enumerate(lines):
        content_start, content, _container_key, block_start, _block_end, text_role = ownership[
            line_index
        ]
        stripped = content.strip(" \t")
        start = content_start + len(content) - len(content.lstrip(" \t"))
        opaque_owner = opaque_cursor.owner_start(start)
        match = _FORMULA_MARKER_LINE_RE.fullmatch(stripped)
        if match is None:
            if (
                stripped == "$$$$"
                and text_role != "heading"
                and _is_text_item_start(ownership, line_index)
                and _is_isolated_text_item(ownership, line_index)
                and not in_ranges(start, code)
                and opaque_owner is None
                and not owned_math_cursor.overlaps(start, start + 4)
            ):
                facts.append(
                    _placeholder_fact(
                        document,
                        smap,
                        start,
                        start + 4,
                        "empty-display-math",
                        complete=True,
                    )
                )
                occupied.append((start, start + 4))
            continue
        end = start + len(stripped)
        if (
            text_role == "heading"
            or not _is_text_item_start(ownership, line_index)
            or not _is_isolated_text_item(ownership, line_index)
            or occupied_cursor.overlaps(start, end)
            or owned_math_cursor.overlaps(start, end)
            or in_ranges(start, code)
        ):
            continue
        if opaque_owner is not None and not _owned_marker_comment(
            line_start, start, stripped, opaque_owner, block_start, content_start
        ):
            continue
        facts.append(
            _placeholder_fact(
                document,
                smap,
                start,
                end,
                _FORMULA_MARKER,
            )
        )
        occupied.append((start, end))

    dollar_occupied_cursor = _RangeCursor(_merge_ranges(occupied))
    dollar_math_cursor = _RangeCursor(owned_math_ranges)
    for start, body_start, body_end, close_end in dollar_ranges:
        if document.text[body_start:body_end].strip():
            continue
        if dollar_occupied_cursor.overlaps(start, close_end) or dollar_math_cursor.overlaps(
            start, close_end
        ):
            continue
        facts.append(
            _placeholder_fact(
                document,
                smap,
                start,
                close_end,
                "empty-display-math",
                complete=True,
            )
        )
        occupied.append((start, close_end))

    image_math_cursor = _RangeCursor(owned_math_ranges)
    image_line_index = 0
    for token in links:
        if (
            not token.is_image
            or token.destination is None
            or in_ranges(token.start, code)
            or image_math_cursor.overlaps(token.start, token.end)
        ):
            continue
        while image_line_index + 1 < len(lines) and token.start >= lines[image_line_index][1]:
            image_line_index += 1
        # A multiline link title belongs to this item; isolate after the token.
        token_end_line_index = image_line_index
        while token_end_line_index + 1 < len(lines) and token.end > lines[token_end_line_index][1]:
            token_end_line_index += 1
        (
            content_start,
            content,
            container_key,
            _block_start,
            _block_end,
            text_role,
        ) = ownership[image_line_index]
        item_start = content_start + len(content) - len(content.lstrip(" \t"))
        (
            token_end_content_start,
            token_end_content,
            token_end_container_key,
            _token_end_block_start,
            _token_end_block_end,
            _token_end_text_role,
        ) = ownership[token_end_line_index]
        item_end = token_end_content_start + len(token_end_content.rstrip(" \t"))
        assert token.image_alt is not None
        if text_role == "heading":
            continue
        if container_key:
            if (
                token.start != item_start
                or token.end != item_end
                or token_end_container_key != container_key
                or not _is_text_item_start(ownership, image_line_index)
                or not _is_isolated_text_item(ownership, token_end_line_index)
            ):
                continue
        elif (
            not _is_standalone_line(document.text, token.start, token.end)
            or not _is_text_item_start(ownership, image_line_index)
            or not _is_isolated_text_item(ownership, token_end_line_index)
        ):
            continue
        alt = token.image_alt.strip()
        destination = token.destination.strip()
        resource = destination.split("#", 1)[0].split("?", 1)[0]
        filename = resource.rsplit("/", 1)[-1]
        if (
            _FORMULA_IMAGE_ALT_RE.fullmatch(alt) is None
            and _FORMULA_IMAGE_NAME_RE.fullmatch(filename) is None
        ):
            continue
        facts.append(
            _placeholder_fact(
                document,
                smap,
                token.start,
                token.end,
                "formula-image",
            )
        )

    return tuple(
        sorted(
            facts,
            key=lambda fact: (fact.span.start if fact.span is not None else -1, fact.fact_id),
        )
    )


def _placeholder_fact(
    document: SourceDocument,
    smap: SourceMap,
    start: int,
    end: int,
    placeholder_kind: GeneratedPlaceholderKind,
    *,
    source_math_fact_id: str | None = None,
    complete: bool | None = None,
) -> GeneratedFormulaFact:
    text = document.text[start:end]
    return GeneratedFormulaFact(
        fact_id=f"{document.path.as_posix()}::generated-formula::{placeholder_kind}::{start}",
        document_id=document.path.as_posix(),
        span=smap.span(start, end),
        raw=text,
        confidence="source",
        kind="candidate",
        text=text,
        candidate_kind="placeholder",
        source_math_fact_id=source_math_fact_id,
        placeholder_kind=placeholder_kind,
        complete=complete,
    )


def _active_math_body(body: str, container: str) -> str:
    """Mask directive options and TeX comments without changing source offsets."""

    active_body = without_tex_comments(body)
    if container != "myst-math-directive":
        return active_body
    prefix_end = 0
    for line in active_body.splitlines(keepends=True):
        line_without_newline = line[:-1] if line.endswith("\n") else line
        if not line_without_newline.strip(" \t\r"):
            prefix_end += len(line)
            continue
        if MYST_OPTION_RE.match(line_without_newline) is None:
            break
        prefix_end += len(line)
    return " " * prefix_end + active_body[prefix_end:]


def _is_standalone_line(text: str, start: int, end: int) -> bool:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].strip(" \t") == text[start:end]


def _is_isolated_text_item(
    line_ownership: Sequence[tuple[int, str, tuple[int, ...], bool, bool, str]],
    index: int,
) -> bool:
    if index + 1 >= len(line_ownership):
        return True
    _content_start, _content, container_key, _block_start, _block_end, _text_role = line_ownership[
        index
    ]
    (
        _next_start,
        next_content,
        next_key,
        next_block_start,
        _next_block_end,
        _next_text_role,
    ) = line_ownership[index + 1]
    return next_key != container_key or next_block_start or not next_content.strip(" \t")
