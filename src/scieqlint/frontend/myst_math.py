"""Math fact lowering for conservative MyST/Markdown input."""

from __future__ import annotations

import re
from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import replace
from urllib.parse import quote

from scieqlint.facts.math import (
    DisplayMathFact,
    InlineDelimiter,
    InlineMathFact,
)
from scieqlint.facts.reference import EquationLabelFact, EquationRefFact
from scieqlint.facts.structure import FenceFact
from scieqlint.io.source import SourceDocument
from scieqlint.markdown import (
    MarkdownReferenceSnapshot,
    is_escaped,
    range_contains,
    scan_tex_lexically,
)
from scieqlint.source.maps import SourceMap

from .myst_blocks import directive_option_prefix_lines
from .myst_shared import (
    DOLLAR_TAIL_LABEL_RE,
    MYST_OPTION_RE,
    TEX_LABEL_RE,
    LineRange,
    OffsetRange,
    dollar_inline_ranges,
    in_ranges,
    line_ranges,
    normalize_label,
)

_MYST_MATH_ROLE_RE = re.compile(r"\{math\}`(?P<body>[^`\r\n]+)`")
_PLAIN_TEXT_RELATIONS = "=<>≤≥→"
_PLAIN_TEXT_OPERATORS = "+-*/^"
_TEX_REFERENCE_RE = re.compile(r"\\(?P<kind>eqref|ref)\{(?P<target>[^{}\r\n]+)\}")


def math_occupied_ranges(
    display_math: Sequence[DisplayMathFact],
) -> tuple[OffsetRange, ...]:
    return tuple(
        sorted((fact.span.start, fact.span.end) for fact in display_math if fact.span is not None)
    )


def scan_display_math(
    document: SourceDocument,
    smap: SourceMap,
    fences: Sequence[FenceFact],
    dollar_ranges: Sequence[tuple[int, int, int, int]],
    occupied: Sequence[OffsetRange] = (),
    fence_occupied: Sequence[OffsetRange] = (),
) -> tuple[
    tuple[DisplayMathFact, ...],
    tuple[EquationLabelFact, ...],
    tuple[EquationRefFact, ...],
]:
    display: list[DisplayMathFact] = []
    labels: list[EquationLabelFact] = []
    references: list[EquationRefFact] = []
    occupied = _merge_occupied(occupied)
    fence_occupied = _merge_occupied(fence_occupied)
    for fence in fences:
        if (
            fence.kind != "math"
            or fence.body_span is None
            or in_ranges(fence.opener_span.start, fence_occupied)
        ):
            continue
        math_fact, label_facts, reference_facts = _math_fact_from_fence(document, smap, fence)
        display.append(math_fact)
        labels.extend(label_facts)
        references.extend(reference_facts)

    dollar_display, dollar_labels, dollar_references = _dollar_display_math(
        document,
        smap,
        tuple(
            dollar_range
            for dollar_range in dollar_ranges
            if not in_ranges(dollar_range[0], occupied)
        ),
    )
    display.extend(dollar_display)
    labels.extend(dollar_labels)
    references.extend(dollar_references)
    return tuple(display), tuple(labels), tuple(references)


def scan_raw_latex_math(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
    bracketed_occupied: Sequence[OffsetRange] = (),
) -> tuple[
    tuple[DisplayMathFact, ...],
    tuple[EquationLabelFact, ...],
    tuple[EquationRefFact, ...],
]:
    """Lower top-level raw-LaTeX environment candidates without classifying them."""

    displays: list[DisplayMathFact] = []
    occupied_ranges = _merge_occupied(occupied)
    bracketed_ranges = _merge_occupied(bracketed_occupied)
    for environment, start, body_start, body_end, end, complete in _raw_math_environment_ranges(
        document.text, occupied_ranges, bracketed_ranges
    ):
        fact_id = f"{document.path.as_posix()}::raw-math::{start}"
        raw = document.text[start:end]
        body_text = document.text[body_start:body_end]
        display = DisplayMathFact(
            fact_id=fact_id,
            document_id=document.path.as_posix(),
            span=smap.span(start, end),
            raw=raw,
            body=body_text.strip(),
            container="raw-latex",
            environment=environment,
            complete=complete,
            source_syntax="raw-latex",
        )
        displays.append(display)
    # Raw environments are lexical candidates only. MathHost decides the final
    # classification and preserves parseable facts for complete non-opaque forms.
    return tuple(displays), (), ()


def _raw_math_environment_ranges(
    text: str,
    occupied: Sequence[OffsetRange],
    bracketed_occupied: Sequence[OffsetRange] = (),
) -> Iterable[tuple[str, int, int, int, int, bool]]:
    stack: list[tuple[str, int, int, bool]] = []
    candidate_malformed = False
    lexical = scan_tex_lexically(text, occupied=(*occupied, *bracketed_occupied))
    for kind, environment, token_start, token_end in lexical.environment_tokens:
        if not stack and (
            in_ranges(token_start, occupied) or in_ranges(token_start, bracketed_occupied)
        ):
            continue
        if kind == "begin":
            if not stack:
                candidate_malformed = False
            stack.append(
                (
                    environment,
                    token_start,
                    token_end,
                    not stack,
                )
            )
            continue
        if not stack:
            continue
        if stack[-1][0] != environment:
            candidate_malformed = True
            continue
        outer_environment, start, body_start, is_candidate = stack.pop()
        if stack or not is_candidate:
            continue
        yield (
            outer_environment,
            start,
            body_start,
            token_start,
            token_end,
            not candidate_malformed,
        )
        candidate_malformed = False
    if stack:
        outer_environment, start, body_start, _ = stack[0]
        yield (
            outer_environment,
            start,
            body_start,
            len(text),
            len(text),
            False,
        )


def scan_inline_math(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
    reference_snapshot: MarkdownReferenceSnapshot,
) -> Iterable[InlineMathFact]:
    facts: list[InlineMathFact] = []
    lines = tuple(line_ranges(document.text))
    dollar_ranges = tuple(dollar_inline_ranges(document.text, occupied))
    dollar_occupied = tuple((start, end) for start, _body_start, _body_end, end in dollar_ranges)
    for start, body_start, body_end, end in dollar_ranges:
        body = document.text[body_start:body_end]
        text = body.strip()
        if not text:
            continue
        span_start = body_start + len(body) - len(body.lstrip())
        span_end = body_start + len(body.rstrip())
        role = reference_snapshot.text_role_at(start)
        facts.append(
            InlineMathFact(
                fact_id=f"{document.path.as_posix()}::inline-math::{start}",
                document_id=document.path.as_posix(),
                span=smap.span(span_start, span_end),
                raw=document.text[start:end],
                body=text,
                delimiter_kind="dollar",
                surrounding_text_role=role,
            )
        )

    explicit_opaque = _merge_occupied(
        (
            *occupied,
            *reference_snapshot.non_math_opaque_ranges,
            *dollar_occupied,
        )
    )
    role_candidates = tuple(
        _delimited_inline_candidates(
            document,
            smap,
            _MYST_MATH_ROLE_RE,
            "myst-role",
            explicit_opaque,
            reference_snapshot,
        )
    )
    facts.extend(fact for fact, _owner_range in role_candidates)
    role_occupied = _merge_occupied(
        (*explicit_opaque, *(owner_range for _fact, owner_range in role_candidates))
    )
    facts.extend(_latex_paren_facts(document, smap, role_occupied, lines, reference_snapshot))

    math_ranges = tuple((fact.span.start, fact.span.end) for fact in facts if fact.span is not None)
    # Link text accepts explicit inline markup, but inferred equation-like text in a
    # label remains prose. Link metadata is already part of ``explicit_opaque``.
    inferred_opaque = _merge_occupied(
        (
            *explicit_opaque,
            *((token.start, token.end) for token in reference_snapshot.links),
            *math_ranges,
        )
    )
    facts.extend(
        _plain_text_math_facts(
            document,
            smap,
            inferred_opaque,
            lines,
            reference_snapshot,
        )
    )
    ordered = sorted(
        facts,
        key=lambda fact: (fact.span.start if fact.span is not None else -1, fact.fact_id),
    )
    yield from _with_accessibility_ids(document, ordered)


def _with_accessibility_ids(
    document: SourceDocument,
    facts: Sequence[InlineMathFact],
) -> Iterable[InlineMathFact]:
    """Assign source-owned IDs without coupling metadata to byte offsets."""

    occurrences: dict[tuple[str, str], int] = {}
    encoded_path = quote(document.path.as_posix(), safe="")
    for fact in facts:
        if fact.delimiter_kind == "plain-text":
            yield fact
            continue
        identity = (fact.delimiter_kind, fact.body)
        occurrence = occurrences.get(identity, 0)
        occurrences[identity] = occurrence + 1
        accessibility_id = (
            f"{encoded_path}::inline-math::{fact.delimiter_kind}::{quote(fact.body, safe='')}"
        )
        if occurrence:
            accessibility_id += f"::{occurrence}"
        yield replace(fact, accessibility_id=accessibility_id)


def _merge_occupied(ranges: Sequence[OffsetRange]) -> tuple[OffsetRange, ...]:
    merged: list[OffsetRange] = []
    for start, end in sorted(ranges):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return tuple(merged)


def _delimited_inline_candidates(
    document: SourceDocument,
    smap: SourceMap,
    pattern: re.Pattern[str],
    delimiter_kind: InlineDelimiter,
    occupied: Sequence[OffsetRange],
    reference_snapshot: MarkdownReferenceSnapshot,
) -> Iterable[tuple[InlineMathFact, OffsetRange]]:
    for match in pattern.finditer(document.text):
        if _overlaps_occupied(match.start(), match.end(), occupied) or is_escaped(
            document.text, match.start()
        ):
            continue
        body = match.group("body")
        text = body.strip()
        if not text:
            continue
        body_start = match.start("body") + len(body) - len(body.lstrip())
        body_end = match.start("body") + len(body.rstrip())
        role = reference_snapshot.text_role_at(match.start())
        yield (
            InlineMathFact(
                fact_id=f"{document.path.as_posix()}::inline-math::{match.start()}",
                document_id=document.path.as_posix(),
                span=smap.span(body_start, body_end),
                raw=match.group(0),
                body=text,
                delimiter_kind=delimiter_kind,
                surrounding_text_role=role,
            ),
            (match.start(), match.end()),
        )


def _latex_paren_facts(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
    lines: Sequence[LineRange],
    reference_snapshot: MarkdownReferenceSnapshot,
) -> Iterable[InlineMathFact]:
    text = document.text
    for line_start, _line_end, line in lines:
        opener: int | None = None
        for match in re.finditer(r"\\[()]|%", line):
            delimiter = match.group(0)
            offset = line_start + match.start()
            if in_ranges(offset, occupied) or is_escaped(text, offset):
                continue
            if opener is not None and _overlaps_occupied(opener, offset, occupied):
                opener = None
            if delimiter == "%":
                if opener is not None:
                    break
                continue
            if delimiter == r"\(":
                if opener is None:
                    opener = offset
                continue
            if opener is None:
                continue
            close = offset
            body = text[opener + 2 : close]
            stripped = body.strip()
            if stripped:
                body_start = opener + 2 + len(body) - len(body.lstrip())
                body_end = opener + 2 + len(body.rstrip())
                yield InlineMathFact(
                    fact_id=f"{document.path.as_posix()}::inline-math::{opener}",
                    document_id=document.path.as_posix(),
                    span=smap.span(body_start, body_end),
                    raw=text[opener : close + 2],
                    body=stripped,
                    delimiter_kind="latex-paren",
                    surrounding_text_role=reference_snapshot.text_role_at(opener),
                )
            opener = None


def _overlaps_occupied(
    start: int,
    end: int,
    occupied: Sequence[OffsetRange],
) -> bool:
    index = bisect_left(occupied, (start, -1))
    if index < len(occupied) and occupied[index][0] < end:
        return True
    return index > 0 and occupied[index - 1][1] > start


def _plain_text_math_facts(
    document: SourceDocument,
    smap: SourceMap,
    occupied: Sequence[OffsetRange],
    lines: Sequence[LineRange],
    reference_snapshot: MarkdownReferenceSnapshot,
) -> Iterable[InlineMathFact]:
    for line_start, _line_end, line in lines:
        for candidate_start, candidate_end in _plain_text_math_candidate_spans(line):
            start = line_start + candidate_start
            end = line_start + candidate_end
            if _overlaps_occupied(start, end, occupied):
                continue
            body = line[candidate_start:candidate_end]
            role = reference_snapshot.text_role_at(start)
            yield InlineMathFact(
                fact_id=f"{document.path.as_posix()}::inline-math-leak::{start}",
                document_id=document.path.as_posix(),
                span=smap.span(start, end),
                raw=body,
                body=body,
                delimiter_kind="plain-text",
                surrounding_text_role=role,
                confidence="inferred",
            )


def _plain_text_math_candidate_spans(line: str) -> Iterable[OffsetRange]:
    """Scan plain-text equation candidates once from left to right."""

    index = 0
    candidate_start: int | None = None
    candidate_has_command = False
    relation_seen = False
    expecting_operand = True
    unary_sign = False
    complete_end: int | None = None
    blocked_until_boundary = False
    while index < len(line):
        if line[index] in " \t":
            if unary_sign:
                # A separated unary sign is an incomplete candidate. Do not
                # publish the complete prefix that precedes it.
                if candidate_start is not None and (candidate_has_command or relation_seen):
                    blocked_until_boundary = True
                candidate_start = None
                candidate_has_command = False
                relation_seen = False
                expecting_operand = True
                unary_sign = False
                complete_end = None
            index += 1
            continue

        token = _plain_text_math_token_at(line, index)
        if blocked_until_boundary:
            if token is None:
                blocked_until_boundary = False
            index = index + 1 if token is None else token[1]
            continue

        if token is None:
            if (
                candidate_start is not None
                and complete_end is not None
                and not expecting_operand
                and _plain_text_candidate_has_boundaries(line, candidate_start, complete_end)
            ):
                yield candidate_start, complete_end
            candidate_start = None
            candidate_has_command = False
            relation_seen = False
            expecting_operand = True
            unary_sign = False
            complete_end = None
            index += 1
            continue

        kind, token_end = token
        if expecting_operand:
            if kind == "atom":
                if candidate_start is None:
                    candidate_start = index
                if line[index] == "\\":
                    candidate_has_command = True
                expecting_operand = False
                unary_sign = False
                if relation_seen:
                    complete_end = token_end
                index = token_end
                continue
            if kind == "operator" and line[index] in "+-" and not unary_sign:
                if candidate_start is None:
                    candidate_start = index
                unary_sign = True
                index = token_end
                continue
            if candidate_start is not None and (candidate_has_command or relation_seen):
                blocked_until_boundary = True
            candidate_start = None
            candidate_has_command = False
            relation_seen = False
            expecting_operand = True
            unary_sign = False
            complete_end = None
            index = token_end
            continue

        if kind == "operator":
            expecting_operand = True
            unary_sign = False
            index = token_end
            continue
        if kind == "relation":
            relation_seen = True
            expecting_operand = True
            unary_sign = False
            complete_end = None
            index = token_end
            continue

        # A subsequent atom without punctuation is an attached group. Keep the
        # whole ambiguous region opaque so a truncated prefix cannot become a
        # fact; punctuation is handled by the token-none branch above.
        if candidate_start is not None and (candidate_has_command or relation_seen):
            blocked_until_boundary = True
            index = token_end
            candidate_start = None
            candidate_has_command = False
            relation_seen = False
            expecting_operand = True
            unary_sign = False
            complete_end = None
            continue
        candidate_start = None
        candidate_has_command = False
        relation_seen = False
        expecting_operand = True
        unary_sign = False
        complete_end = None
        # Reprocess an atom after resetting so an independent candidate can
        # start at the same token.

    if (
        candidate_start is not None
        and complete_end is not None
        and not expecting_operand
        and not blocked_until_boundary
        and _plain_text_candidate_has_boundaries(line, candidate_start, complete_end)
    ):
        yield candidate_start, complete_end


def _plain_text_math_token_at(line: str, index: int) -> tuple[str, int] | None:
    character = line[index]
    if character in _PLAIN_TEXT_RELATIONS:
        end = index + 1
        if character in "<>" and end < len(line) and line[end] == "=":
            end += 1
        return "relation", end
    if character in _PLAIN_TEXT_OPERATORS:
        return "operator", index + 1
    if character == "\\":
        end = index + 1
        while end < len(line) and line[end].isascii() and line[end].isalpha():
            end += 1
        return ("atom", end) if end > index + 1 else None
    if character.isascii() and character.isdigit():
        end = index + 1
        while end < len(line) and line[end].isascii() and line[end].isdigit():
            end += 1
        if (
            end + 1 < len(line)
            and line[end] == "."
            and line[end + 1].isascii()
            and line[end + 1].isdigit()
        ):
            end += 2
            while end < len(line) and line[end].isascii() and line[end].isdigit():
                end += 1
        return "atom", end
    if (
        character == "."
        and index + 1 < len(line)
        and line[index + 1].isascii()
        and line[index + 1].isdigit()
    ):
        end = index + 2
        while end < len(line) and line[end].isascii() and line[end].isdigit():
            end += 1
        return "atom", end
    if (character.isascii() and character.isalpha()) or character in "_{}":
        end = index + 1
        while end < len(line) and (
            (line[end].isascii() and line[end].isalnum()) or line[end] in "_{}"
        ):
            end += 1
        if end < len(line) and line[end] == "(":
            close = end + 1
            while close < len(line) and line[close] not in "()\r\n":
                close += 1
            if close < len(line) and line[close] == ")":
                end = close + 1
        return "atom", end
    return None


def _plain_text_candidate_has_boundaries(line: str, start: int, end: int) -> bool:
    if start > 0 and (line[start - 1].isalnum() or line[start - 1] in "_$."):
        return False
    if end >= len(line):
        return True
    if line[end] in "([{)]}":
        return False
    delimiter_end = end
    while delimiter_end < len(line) and line[delimiter_end] in " \t":
        delimiter_end += 1
    if delimiter_end < len(line) and line[delimiter_end] in "([{)]}":
        return False
    if line[end].isalnum() or line[end] in "_$":
        return False
    return not (line[end] == "." and end + 1 < len(line) and line[end + 1].isdigit())


def _math_fact_from_fence(
    document: SourceDocument,
    smap: SourceMap,
    fence: FenceFact,
) -> tuple[
    DisplayMathFact,
    tuple[EquationLabelFact, ...],
    tuple[EquationRefFact, ...],
]:
    assert fence.body_span is not None
    body_text = document.text[fence.body_span.start : fence.body_span.end]
    body = body_text.strip()
    fact_id = f"{fence.fact_id}::math"
    option_prefix_length = 0
    if fence.info_string == "{math}":
        for _line_start, line_end, line in directive_option_prefix_lines(document, fence):
            if MYST_OPTION_RE.match(line) is None:
                break
            option_prefix_length = line_end - fence.body_span.start
    labels: list[EquationLabelFact] = []
    references: tuple[EquationRefFact, ...] = ()
    if fence.is_closed:
        labels.extend(_tex_label_facts(document, smap, fact_id, fence.body_span.start, body_text))
        references = tuple(
            _tex_reference_facts(document, smap, fact_id, fence.body_span.start, body_text)
        )
        if fence.info_string == "{math}":
            labels.extend(_myst_math_label_facts(document, smap, fact_id, fence))
    return (
        DisplayMathFact(
            fact_id=fact_id,
            document_id=fence.document_id,
            span=fence.body_span,
            raw=body,
            body=body,
            container=("myst-math-directive" if fence.info_string == "{math}" else "fenced-math"),
            option_prefix_length=option_prefix_length,
            label_fact_ids=tuple(label.fact_id for label in labels),
            complete=fence.is_closed,
        ),
        tuple(labels),
        references,
    )


def _dollar_display_math(
    document: SourceDocument,
    smap: SourceMap,
    dollar_ranges: Sequence[tuple[int, int, int, int]],
) -> tuple[
    tuple[DisplayMathFact, ...],
    tuple[EquationLabelFact, ...],
    tuple[EquationRefFact, ...],
]:
    display: list[DisplayMathFact] = []
    labels: list[EquationLabelFact] = []
    references: list[EquationRefFact] = []
    for start, body_start, body_end, _close_end in dollar_ranges:
        fact_id = f"{document.path.as_posix()}::display-math::{start}"
        body_text = document.text[body_start:body_end]
        body = body_text.strip()
        if not body:
            continue
        span_start = body_start + len(body_text) - len(body_text.lstrip())
        span_end = body_start + len(body_text.rstrip())
        label_facts = list(_tex_label_facts(document, smap, fact_id, body_start, body_text))
        label_facts.extend(_dollar_tail_label_facts(document, smap, fact_id, body_end))
        reference_facts = tuple(
            _tex_reference_facts(document, smap, fact_id, body_start, body_text)
        )
        labels.extend(label_facts)
        references.extend(reference_facts)
        display.append(
            DisplayMathFact(
                fact_id=fact_id,
                document_id=document.path.as_posix(),
                span=smap.span(span_start, span_end),
                raw=body,
                body=body,
                container="dollar-dollar",
                label_fact_ids=tuple(label.fact_id for label in label_facts),
            )
        )
    return tuple(display), tuple(labels), tuple(references)


def _tex_reference_facts(
    document: SourceDocument,
    smap: SourceMap,
    fact_id: str,
    body_start: int,
    body_text: str,
) -> Iterable[EquationRefFact]:
    lexical = scan_tex_lexically(body_text)
    active_body = lexical.active_text
    for match in _TEX_REFERENCE_RE.finditer(active_body):
        if is_escaped(body_text, match.start()) or range_contains(
            match.start(), lexical.non_math_ranges
        ):
            continue
        target = match.group("target").strip()
        if not target:
            continue
        raw_target = match.group("target")
        leading = len(raw_target) - len(raw_target.lstrip())
        target_start = body_start + match.start("target") + leading
        role_start = body_start + match.start()
        role_end = body_start + match.end()
        yield EquationRefFact(
            fact_id=f"{fact_id}::ref::{target_start}",
            document_id=document.path.as_posix(),
            span=smap.span(role_start, role_end),
            raw=match.group(0),
            ref_kind=f"tex-{match.group('kind')}",
            target=target,
            normalized_target=normalize_label(target),
            source_block_id=fact_id,
            role_span=smap.span(role_start, role_end),
            target_span=smap.span(target_start, target_start + len(target)),
        )


def _tex_label_facts(
    document: SourceDocument,
    smap: SourceMap,
    fact_id: str,
    body_start: int,
    body_text: str,
) -> Iterable[EquationLabelFact]:
    lexical = scan_tex_lexically(body_text)
    active_body = lexical.active_text
    for match in TEX_LABEL_RE.finditer(active_body):
        if is_escaped(body_text, match.start()) or range_contains(
            match.start(), lexical.non_math_ranges
        ):
            continue
        label = match.group("label")
        if not label.strip():
            continue
        label_start = body_start + match.start("label")
        yield EquationLabelFact(
            fact_id=f"{fact_id}::label::{label_start}",
            document_id=document.path.as_posix(),
            span=smap.span(label_start, label_start + len(label)),
            raw=label,
            label=label,
            normalized_label=normalize_label(label),
            label_syntax_kind="tex-label",
            source_block_id=fact_id,
            label_span=smap.span(label_start, label_start + len(label)),
        )


def _myst_math_label_facts(
    document: SourceDocument,
    smap: SourceMap,
    fact_id: str,
    fence: FenceFact,
) -> Iterable[EquationLabelFact]:
    assert fence.body_span is not None
    for line_start, _line_end, line in directive_option_prefix_lines(document, fence):
        match = MYST_OPTION_RE.match(line)
        if match is None:
            break
        if match.group("key") != "label":
            continue
        label = match.group("value").strip()
        if not label:
            continue
        label_start = line_start + match.start("value")
        yield EquationLabelFact(
            fact_id=f"{fact_id}::label::{label_start}",
            document_id=document.path.as_posix(),
            span=smap.span(label_start, label_start + len(label)),
            raw=label,
            label=label,
            normalized_label=normalize_label(label),
            label_syntax_kind="myst-directive-option",
            source_block_id=fact_id,
            label_span=smap.span(label_start, label_start + len(label)),
        )


def _dollar_tail_label_facts(
    document: SourceDocument,
    smap: SourceMap,
    fact_id: str,
    close: int,
) -> Iterable[EquationLabelFact]:
    line_end = document.text.find("\n", close)
    if line_end == -1:
        line_end = len(document.text)
    tail_start = close + 2
    tail = document.text[tail_start:line_end]
    leading = len(tail) - len(tail.lstrip(" \t"))
    trailing = len(tail.rstrip(" \t"))
    candidate = tail[leading:trailing]
    match = DOLLAR_TAIL_LABEL_RE.fullmatch(candidate)
    if match is None:
        return
    group_name = "brace" if match.group("brace") else "paren"
    label = match.group(group_name)
    assert label is not None
    label_start = tail_start + leading + match.start(group_name)
    yield EquationLabelFact(
        fact_id=f"{fact_id}::label::{label_start}",
        document_id=document.path.as_posix(),
        span=smap.span(label_start, label_start + len(label)),
        raw=label,
        label=label,
        normalized_label=normalize_label(label),
        label_syntax_kind="dollar-tail",
        source_block_id=fact_id,
        label_span=smap.span(label_start, label_start + len(label)),
    )
