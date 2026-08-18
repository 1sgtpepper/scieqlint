"""MathHost classification for frontend-produced inline math candidates."""

from __future__ import annotations

import re
from dataclasses import replace

from scieqlint.facts.math import (
    InlineMathFact,
    InlineParseStatus,
    UnknownMathFact,
    UnknownReason,
)
from scieqlint.facts.snapshot import FactSnapshot

_UNSUPPORTED_ENVIRONMENT_RE = re.compile(r"(?<!\\)\\(?:begin|end)\{(?P<environment>[A-Za-z]+\*?)\}")
_MISSING_BRACED_ARGUMENT_RE = re.compile(r"\\(?:frac|dfrac|tfrac|binom)\s*\{[^{}]*\}\s*$")
_TRAILING_OPERATOR_RE = re.compile(r"(?:[+\-*/^=]|<=|>=|<|>|\\(?:le|ge))\s*$")
_RELATION_RE = re.compile(r"(?:=|<=|>=|<|>|≤|≥|→)")
_OPENING_DELIMITERS = {"(": ")", "[": "]", "{": "}"}
_CLOSING_DELIMITERS = {value: key for key, value in _OPENING_DELIMITERS.items()}


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
        return replace(
            snapshot,
            inline_math=tuple(inline_math),
            unknown_math=(*snapshot.unknown_math, *unknown_math),
        )


def _classify_inline(
    fact: InlineMathFact,
) -> tuple[InlineParseStatus, UnknownMathFact | None]:
    if fact.delimiter_kind == "plain-text":
        if _looks_like_plain_text_math(fact.body):
            return "text-leak", None
        return "preserved", None

    environment = _UNSUPPORTED_ENVIRONMENT_RE.search(fact.body)
    if environment is not None:
        return "unsupported", _unknown(fact, "environment", environment.group("environment"))
    if (
        not _balanced_delimiters(fact.body)
        or _MISSING_BRACED_ARGUMENT_RE.search(fact.body)
        or _TRAILING_OPERATOR_RE.search(fact.body)
    ):
        return "unsupported", _unknown(fact, "unsupported_syntax", fact.body[:80])
    return "preserved", None


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
    """Accept only equation candidates with a compact mathematical signal."""

    if _RELATION_RE.search(body) is None:
        return False
    if any(character in body for character in "_+*/^\\"):
        return True
    atoms = re.findall(r"[A-Za-z]+", body)
    return bool(atoms) and all(len(atom) == 1 for atom in atoms)


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
