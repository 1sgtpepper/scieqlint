"""Ordinary inline and display math classification."""

from __future__ import annotations

import re
from dataclasses import replace

from scieqlint.facts.math import (
    DisplayMathFact,
    InlineMathFact,
    InlineParseStatus,
    UnknownMathFact,
    UnknownReason,
)
from scieqlint.markdown import is_escaped, scan_tex_lexically, without_tex_comments

_UNSUPPORTED_ENVIRONMENT_RE = re.compile(r"\\(?:begin|end)\{(?P<environment>[^{}\s]+)\}")
_REQUIRED_ARITY_COMMAND_RE = re.compile(r"\\(?:frac|dfrac|tfrac|binom)(?![A-Za-z])")
_RELATION_OPERATOR = r"(?:<=|>=|=|<|>|≤|≥|→|\\(?:leq?|geq?))"
_TRAILING_OPERATOR_RE = re.compile(rf"(?:[+\-*/^]|{_RELATION_OPERATOR})\s*$")
_RELATION_RE = re.compile(_RELATION_OPERATOR)
_COMPACT_SUBSCRIPT_RE = re.compile(r"(?<![A-Za-z])(?:[A-Za-z]|\d)_(?:[A-Za-z0-9]|\{[^{}\r\n]+\})")
_TEX_COMMAND_RE = re.compile(r"\\[A-Za-z]+")
_OPENING_DELIMITERS = {"(": ")", "[": "]", "{": "}"}
_CLOSING_DELIMITERS = {value: key for key, value in _OPENING_DELIMITERS.items()}
_AMS_ENVIRONMENTS = frozenset({"align", "align*", "aligned", "alignedat", "split"})
_SUPPORTED_RAW_ENVIRONMENTS = frozenset(
    {
        "align",
        "align*",
        "equation",
        "equation*",
        "flalign",
        "flalign*",
        "gather",
        "gather*",
        "multline",
        "multline*",
    }
)


def classify_display(
    fact: DisplayMathFact,
) -> tuple[DisplayMathFact, UnknownMathFact | None]:
    """Resolve AMS semantics after the frontend has preserved display identity."""

    if fact.container == "latex-display":
        return fact, None
    if fact.container == "raw-latex":
        environment = fact.environment
        if environment not in _SUPPORTED_RAW_ENVIRONMENTS:
            return fact, _unknown(fact, "environment", environment or "<missing>")
        if not fact.complete:
            return fact, _unknown(fact, "parse_limit", environment)
        return replace(fact, container="ams"), None

    if not fact.complete:
        return fact, None
    environment = _complete_ams_environment(fact.body)
    if environment is None:
        return fact, None
    return replace(fact, container="ams", environment=environment), None


def _complete_ams_environment(body: str) -> str | None:
    stack: list[str] = []
    selected: str | None = None
    selected_closed = False
    for kind, environment, _start, _end in scan_tex_lexically(body).environment_tokens:
        if kind == "begin":
            stack.append(environment)
            if selected is None and environment in _AMS_ENVIRONMENTS:
                selected = environment
            continue
        if not stack or stack[-1] != environment:
            return None
        stack.pop()
        if selected == environment:
            selected_closed = True
    if selected is None or not selected_closed or stack:
        return None
    return selected


def classify_inline(
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
        or has_missing_required_argument(body)
        or _TRAILING_OPERATOR_RE.search(body)
    ):
        return "unsupported", _unknown(fact, "unsupported_syntax", fact.body[:80])
    return "preserved", None


def has_missing_required_argument(body: str) -> bool:
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
    fact: InlineMathFact | DisplayMathFact,
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
