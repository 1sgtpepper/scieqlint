"""MathHost classification for frontend-produced inline math candidates."""

from __future__ import annotations

import re
from dataclasses import replace

from scieqlint.facts.generated import GeneratedFormulaFact, GeneratedFormulaKind
from scieqlint.facts.math import (
    InlineMathFact,
    InlineParseStatus,
    UnknownMathFact,
    UnknownReason,
)
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.markdown import is_escaped, without_tex_comments
from scieqlint.source.maps import SourceMap

_UNSUPPORTED_ENVIRONMENT_RE = re.compile(r"\\(?:begin|end)\{(?P<environment>[^{}\s]+)\}")
_REQUIRED_ARITY_COMMAND_RE = re.compile(r"\\(?:frac|dfrac|tfrac|binom)(?![A-Za-z])")
_RELATION_OPERATOR = r"(?:<=|>=|=|<|>|≤|≥|→|\\(?:leq?|geq?))"
_TRAILING_OPERATOR_RE = re.compile(rf"(?:[+\-*/^]|{_RELATION_OPERATOR})\s*$")
_RELATION_RE = re.compile(_RELATION_OPERATOR)
_COMPACT_SUBSCRIPT_RE = re.compile(r"(?<![A-Za-z])(?:[A-Za-z]|\d)_(?:[A-Za-z0-9]|\{[^{}\r\n]+\})")
_TEX_COMMAND_RE = re.compile(r"\\[A-Za-z]+")
_OPENING_DELIMITERS = {"(": ")", "[": "]", "{": "}"}
_CLOSING_DELIMITERS = {value: key for key, value in _OPENING_DELIMITERS.items()}
_MAX_SPACED_TOKEN_PARTS = 64
_SPACED_COMMAND_RE = re.compile(
    rf"(?P<artifact>"
    rf"\\[ \t]*(?:[A-Za-z][ \t]+){{3,{_MAX_SPACED_TOKEN_PARTS}}}[A-Za-z](?=[ \t]*[\[{{])"
    rf"|(?<![A-Za-z0-9_\\])[A-Z](?:[ \t]+[A-Za-z]){{3,{_MAX_SPACED_TOKEN_PARTS}}}"
    rf"(?=[ \t]*\([ \t]*[A-Za-z][ \t]*(?:,[ \t]*[A-Za-z][ \t]*){{2,{_MAX_SPACED_TOKEN_PARTS}}}\))"
    rf")"
)
_GARBLED_MARKER_RE = re.compile(r"(?<![A-Za-z0-9_])(?P<artifact>/C0[ \t]+apod)(?![A-Za-z0-9_])")


class MathHost:
    """Classify inline math after the frontend has preserved source identity."""

    def classify(self, snapshot: FactSnapshot) -> FactSnapshot:
        inline_math: list[InlineMathFact] = []
        unknown_math: list[UnknownMathFact] = []
        existing_unknown_ids = {fact.source_math_fact_id for fact in snapshot.unknown_math}
        for fact in snapshot.inline_math:
            status, unknown = _classify_inline(fact)
            inline_math.append(replace(fact, parse_status=status))
            if unknown is not None and fact.fact_id not in existing_unknown_ids:
                unknown_math.append(unknown)
        classified = replace(
            snapshot,
            inline_math=tuple(inline_math),
            unknown_math=(*snapshot.unknown_math, *unknown_math),
        )
        return replace(
            classified,
            generated_formulas=_classify_generated_formulas(classified),
        )


def _classify_inline(
    fact: InlineMathFact,
) -> tuple[InlineParseStatus, UnknownMathFact | None]:
    if fact.delimiter_kind == "plain-text":
        if _looks_like_plain_text_math(fact.body):
            return "text-leak", None
        return "not-math", None

    body = without_tex_comments(fact.body)
    if fact.delimiter_kind == "latex-paren":
        ambiguous_delimiter = next(
            (
                match
                for match in re.finditer(r"\\[()]", body)
                if not is_escaped(body, match.start())
            ),
            None,
        )
        if ambiguous_delimiter is not None:
            return "unsupported", _unknown(
                fact,
                "ambiguous_delimiter",
                ambiguous_delimiter.group(0),
            )
    environment = next(
        (
            match
            for match in _UNSUPPORTED_ENVIRONMENT_RE.finditer(body)
            if not is_escaped(body, match.start())
        ),
        None,
    )
    if environment is not None:
        return "unsupported", _unknown(fact, "environment", environment.group("environment"))
    if (
        not _balanced_delimiters(body)
        or _has_missing_required_argument(body)
        or _TRAILING_OPERATOR_RE.search(body)
    ):
        return "unsupported", _unknown(fact, "unsupported_syntax", fact.body[:80])
    return "preserved", None


def _has_missing_required_argument(body: str) -> bool:
    commands = tuple(
        command
        for command in _REQUIRED_ARITY_COMMAND_RE.finditer(body)
        if not is_escaped(body, command.start())
    )
    if not commands:
        return False
    brace_ends = _braced_argument_ends(body)
    for command in commands:
        first_end = _tex_argument_end(body, command.end(), brace_ends)
        if first_end is None:
            return True
        if _tex_argument_end(body, first_end, brace_ends) is None:
            return True
    return False


def _braced_argument_ends(body: str) -> dict[int, int]:
    ends: dict[int, int] = {}
    stack: list[int] = []
    index = 0
    while index < len(body):
        character = body[index]
        if character == "\\":
            index += 2
            continue
        if character == "{":
            stack.append(index)
        elif character == "}" and stack:
            ends[stack.pop()] = index + 1
        index += 1
    return ends


def _tex_argument_end(body: str, start: int, brace_ends: dict[int, int]) -> int | None:
    index = _skip_tex_space(body, start)
    if index >= len(body) or body[index] == "%":
        return None
    if body[index] == "{":
        return brace_ends.get(index)
    if body[index] == "\\":
        cursor = index + 1
        if cursor >= len(body):
            return None
        if body[cursor].isalpha():
            while cursor < len(body) and body[cursor].isalpha():
                cursor += 1
        else:
            cursor += 1
        return cursor
    return index + 1


def _skip_tex_space(body: str, start: int) -> int:
    index = start
    while index < len(body) and body[index].isspace():
        index += 1
    return index


def _unknown(
    fact: InlineMathFact,
    reason: UnknownReason,
    excerpt: str,
) -> UnknownMathFact:
    return UnknownMathFact(
        fact_id=f"{fact.fact_id}::unknown",
        document_id=fact.document_id,
        span=fact.span,
        raw=fact.raw,
        source_math_fact_id=fact.fact_id,
        reason=reason,
        excerpt=excerpt,
    )


def _looks_like_plain_text_math(body: str) -> bool:
    """Accept only equation candidates with a structural mathematical signal."""

    has_tex_command = _TEX_COMMAND_RE.search(body) is not None
    has_compact_subscript = _COMPACT_SUBSCRIPT_RE.search(body) is not None
    operand_text = _TEX_COMMAND_RE.sub("", body)
    operand_text = _COMPACT_SUBSCRIPT_RE.sub("x", operand_text)
    relation = _RELATION_RE.search(operand_text)
    if relation is None:
        return False
    atoms = re.findall(r"[A-Za-z]+", operand_text)
    if (
        has_tex_command
        or has_compact_subscript
        or (atoms and all(len(atom) <= 2 for atom in atoms))
    ):
        return True
    for operand in (operand_text[: relation.start()], operand_text[relation.end() :]):
        operators = tuple(re.finditer(r"[+\-*/^]", operand))
        if not operators:
            continue
        if any(char.isdigit() for char in operand):
            return True
        first_nonspace = len(operand) - len(operand.lstrip(" \t"))
        for operator in operators:
            if operator.group(0) in "+-" and operator.start() == first_nonspace:
                continue
            if (
                operator.start() > 0
                and operand[operator.start() - 1] in " \t"
                or operator.end() < len(operand)
                and operand[operator.end()] in " \t"
            ):
                return True
    return False


def _balanced_delimiters(body: str) -> bool:
    stack: list[str] = []
    index = 0
    while index < len(body):
        character = body[index]
        if character == "\\":
            index += 2
            continue
        if character in _OPENING_DELIMITERS:
            stack.append(character)
        elif character in _CLOSING_DELIMITERS and (
            not stack or stack.pop() != _CLOSING_DELIMITERS[character]
        ):
            return False
        index += 1
    return not stack


def _classify_generated_formulas(snapshot: FactSnapshot) -> tuple[GeneratedFormulaFact, ...]:
    source_maps = {
        document.path.as_posix(): SourceMap.for_document(document)
        for document in snapshot.documents
    }
    inline_math = {fact.fact_id: fact for fact in snapshot.inline_math}
    facts: list[GeneratedFormulaFact] = []
    for candidate in snapshot.generated_formulas:
        if candidate.kind != "candidate":
            facts.append(candidate)
            continue
        source_map = source_maps.get(candidate.document_id)
        assert source_map is not None
        assert candidate.span is not None
        facts.extend(_classify_generated_candidate(candidate, source_map, inline_math))
    return tuple(
        sorted(
            facts,
            key=lambda fact: (fact.span.start if fact.span is not None else -1, fact.fact_id),
        )
    )


def _classify_generated_candidate(
    candidate: GeneratedFormulaFact,
    source_map: SourceMap,
    inline_math: dict[str, InlineMathFact],
) -> tuple[GeneratedFormulaFact, ...]:
    if candidate.candidate_kind == "formula-text":
        return _suspicious_formula_facts(candidate, source_map)
    if candidate.candidate_kind == "bracketed-block":
        assert candidate.delimiter_kind is not None
        return (
            replace(
                candidate,
                kind="bracketed-block",
                candidate_kind=None,
                delimiter_kind=candidate.delimiter_kind,
            ),
        )
    if candidate.candidate_kind == "placeholder":
        if candidate.placeholder_kind == "empty-display-math":
            kind: GeneratedFormulaKind = "empty-display"
        elif candidate.placeholder_kind == "formula-image":
            kind = "image-placeholder"
        else:
            kind = "placeholder"
        return (replace(candidate, kind=kind, candidate_kind=None),)
    if candidate.candidate_kind != "equation-like-text" or candidate.source_math_fact_id is None:
        return ()
    source_math = inline_math.get(candidate.source_math_fact_id)
    if source_math is None or source_math.parse_status != "text-leak":
        return ()
    return (
        replace(
            candidate,
            kind="equation-like-text",
            candidate_kind=None,
            confidence="inferred",
        ),
    )


def _suspicious_formula_facts(
    candidate: GeneratedFormulaFact,
    source_map: SourceMap,
) -> tuple[GeneratedFormulaFact, ...]:
    assert candidate.span is not None
    patterns: tuple[tuple[GeneratedFormulaKind, re.Pattern[str]], ...] = (
        ("spaced-token", _SPACED_COMMAND_RE),
        ("garbled-marker", _GARBLED_MARKER_RE),
    )
    facts: list[GeneratedFormulaFact] = []
    active_text = without_tex_comments(candidate.text)
    for kind, pattern in patterns:
        for match in pattern.finditer(active_text):
            local_start, local_end = match.span("artifact")
            artifact = candidate.text[local_start:local_end]
            if kind == "spaced-token":
                if artifact.startswith("\\") and is_escaped(candidate.text, local_start):
                    continue
                if not artifact.startswith("\\") and not _starts_spaced_token_run(
                    active_text, local_start
                ):
                    continue
                if not _high_confidence_spaced_command(artifact):
                    continue
            start = candidate.span.start + local_start
            end = candidate.span.start + local_end
            facts.append(
                GeneratedFormulaFact(
                    fact_id=f"{candidate.document_id}::generated-formula::{kind}::{start}",
                    document_id=candidate.document_id,
                    span=source_map.span(start, end),
                    raw=artifact,
                    confidence="inferred",
                    kind=kind,
                    text=artifact,
                    candidate_kind=None,
                    source_math_fact_id=candidate.source_math_fact_id,
                )
            )
    return tuple(facts)


def _starts_spaced_token_run(text: str, start: int) -> bool:
    # A bounded regex match must not restart inside a longer continuous run.
    end = start
    while end > 0 and text[end - 1] in " \t":
        end -= 1
    if end == start:
        return True
    previous = text[max(0, end - 2) : end]
    return re.fullmatch(r"(?:[^A-Za-z0-9_])?[A-Za-z]", previous) is None


def _high_confidence_spaced_command(artifact: str) -> bool:
    letters = re.findall(r"[A-Za-z]", artifact)
    return len(letters) >= 4 and sum(letter.islower() for letter in letters) >= 2
