"""Typst output-portability classification for source math."""

from __future__ import annotations

import re
from bisect import bisect_left
from collections.abc import Sequence

from scieqlint.facts.math import DisplayMathFact
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.markdown import is_escaped, range_contains, scan_tex_lexically
from scieqlint.source.maps import SourceMap

_TYPST_UNSUPPORTED_COMMAND_RE = re.compile(r"\\(?P<command>dfrac|argmin)(?![A-Za-z])")
_TYPST_DELIMITER_RE = re.compile(r"\\(?P<delimiter>left|right)(?![A-Za-z])")


def typst_math_risks(
    snapshot: FactSnapshot,
) -> tuple[OutputPortabilityFact, ...]:
    """Return focused, source-spanned risks for Typst display-math export."""

    documents = {document.path.as_posix(): document for document in snapshot.documents}
    risks: list[OutputPortabilityFact] = []
    for display in snapshot.display_math:
        if display.span is None:
            continue
        document = documents.get(display.document_id)
        if document is None:
            continue
        source = document.text[display.span.start : display.span.end]
        prefix = display.option_prefix_length
        lexical = scan_tex_lexically(" " * prefix + source[prefix:])
        segment = _mask_non_math_tex_ranges(lexical.active_text, lexical.non_math_ranges)
        environment_tokens = tuple(
            token
            for token in lexical.environment_tokens
            if not range_contains(token[2], lexical.non_math_ranges)
        )
        smap = SourceMap.for_document(document)
        risks.extend(_typst_command_risks(display, segment, smap))
        risks.extend(
            _typst_environment_risks(
                display,
                segment,
                environment_tokens,
                smap,
            )
        )
    return tuple(
        sorted(
            risks,
            key=lambda fact: (
                fact.span.start if fact.span is not None else -1,
                fact.fact_id,
            ),
        )
    )



def _mask_non_math_tex_ranges(
    text: str,
    ranges: Sequence[tuple[int, int]],
) -> str:
    """Mask opaque TeX environments without changing source offsets."""

    masked = list(text)
    for start, end in ranges:
        masked[start:end] = [" "] * (end - start)
    return "".join(masked)


def _typst_command_risks(
    display: DisplayMathFact,
    segment: str,
    smap: SourceMap,
) -> list[OutputPortabilityFact]:
    assert display.span is not None
    risks: list[OutputPortabilityFact] = []
    for match in _TYPST_UNSUPPORTED_COMMAND_RE.finditer(segment):
        if is_escaped(segment, match.start()):
            continue
        start = display.span.start + match.start()
        end = display.span.start + match.end()
        command = match.group("command")
        risks.append(
            OutputPortabilityFact(
                fact_id=f"{display.fact_id}::typst-command::{start}",
                document_id=display.document_id,
                span=smap.span(start, end),
                raw=match.group(0),
                confidence=display.confidence,
                subject_fact_id=display.fact_id,
                output_profile="typst",
                risk_kind="typst-unsupported-command",
                metadata=(
                    ("syntax_kind", "command"),
                    ("token", match.group(0)),
                    ("command", command),
                ),
            )
        )
    return risks


def _typst_environment_risks(
    display: DisplayMathFact,
    segment: str,
    environment_tokens: Sequence[tuple[str, str, int, int]],
    smap: SourceMap,
) -> list[OutputPortabilityFact]:
    assert display.span is not None
    environments, delimiter_commands, delimiter_intervals = _typst_structure(
        segment,
        environment_tokens,
    )
    if not delimiter_commands:
        return []

    delimiter_positions = {
        delimiter: tuple(
            position for position, command in delimiter_commands if command == delimiter
        )
        for delimiter in ("left", "right")
    }
    interval_ends: dict[str, int] = dict.fromkeys(("left", "right", "both"), -1)
    interval_index = 0
    risks: list[OutputPortabilityFact] = []
    for environment_start, environment_end, environment in environments:
        while (
            interval_index < len(delimiter_intervals)
            and delimiter_intervals[interval_index][0] <= environment_start
        ):
            _start, end, kind = delimiter_intervals[interval_index]
            interval_ends[kind] = max(interval_ends[kind], end)
            interval_index += 1

        relevant_positions: list[tuple[int, str]] = []
        for delimiter, positions in delimiter_positions.items():
            position_index = bisect_left(positions, environment_start)
            if position_index < len(positions) and positions[position_index] < environment_end:
                relevant_positions.append((positions[position_index], delimiter))
        if interval_ends["left"] >= environment_end:
            relevant_positions.append((environment_start - 1, "left"))
        if interval_ends["both"] >= environment_end:
            relevant_positions.extend(((environment_start - 1, "left"), (environment_end, "right")))
        if interval_ends["right"] >= environment_end:
            relevant_positions.append((environment_end, "right"))
        if not relevant_positions:
            continue
        delimiters = tuple(
            dict.fromkeys(delimiter for _position, delimiter in sorted(relevant_positions))
        )
        start = display.span.start + environment_start
        token_length = len(f"\\begin{{{environment}}}")
        token_end = start + token_length
        risks.append(
            OutputPortabilityFact(
                fact_id=f"{display.fact_id}::typst-environment::{start}",
                document_id=display.document_id,
                span=smap.span(start, token_end),
                raw=segment[environment_start : environment_start + token_length],
                confidence=display.confidence,
                subject_fact_id=display.fact_id,
                output_profile="typst",
                risk_kind="typst-fragile-environment",
                metadata=(
                    ("syntax_kind", "environment"),
                    ("environment", environment),
                    ("delimiter_commands", ",".join(delimiters)),
                ),
            )
        )
    return risks


def _typst_structure(
    segment: str,
    environment_tokens: Sequence[tuple[str, str, int, int]],
) -> tuple[
    tuple[tuple[int, int, str], ...],
    tuple[tuple[int, str], ...],
    tuple[tuple[int, int, str], ...],
]:
    """Parse environment extents and delimiter intervals in one structural pass."""

    environment_stack: list[tuple[str, int, int | None]] = []
    environments: list[tuple[int, int, str]] = []
    delimiter_commands: list[tuple[int, str]] = []
    delimiter_intervals: list[tuple[int, int, str]] = []
    unmatched_right_intervals: list[tuple[int, int, str]] = []
    delimiter_stack: list[int] = []
    fragile_environments = {"aligned", "array", "matrix"}

    events = [
        (start, end, kind, environment) for kind, environment, start, end in environment_tokens
    ]
    events.extend(
        (match.start(), match.end(), "delimiter", match.group("delimiter"))
        for match in _TYPST_DELIMITER_RE.finditer(segment)
        if not is_escaped(segment, match.start())
    )
    for start, end, kind, value in sorted(events):
        if kind != "delimiter":
            environment = value
            if kind == "begin":
                environment_index: int | None = None
                if environment in fragile_environments:
                    environment_index = len(environments)
                    environments.append((start, len(segment), environment))
                environment_stack.append((environment, start, environment_index))
                continue
            if not environment_stack or environment_stack[-1][0] != environment:
                continue
            _opened_environment, opened_at, environment_index = environment_stack.pop()
            if environment_index is not None:
                environments[environment_index] = (opened_at, end, environment)
            continue

        delimiter = value
        delimiter_commands.append((start, delimiter))
        if delimiter == "left":
            delimiter_stack.append(len(delimiter_intervals))
            delimiter_intervals.append((start, len(segment), "left"))
            continue
        if delimiter_stack:
            interval_index = delimiter_stack.pop()
            delimiter_intervals[interval_index] = (
                delimiter_intervals[interval_index][0],
                end,
                "both",
            )
        else:
            unmatched_right_intervals.append((0, end, "right"))

    for interval_index in delimiter_stack:
        start, _end, kind = delimiter_intervals[interval_index]
        delimiter_intervals[interval_index] = (start, len(segment), kind)
    for environment, start, environment_index in environment_stack:
        if environment_index is not None:
            environments[environment_index] = (start, len(segment), environment)

    return (
        tuple(environments),
        tuple(delimiter_commands),
        (*unmatched_right_intervals, *delimiter_intervals),
    )
