"""MathHost: classify math facts and produce ``UnknownMath`` facts."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import cast

from scieqlint.facts.math import (
    DisplayMathFact,
    InlineMathFact,
    SuspiciousFormulaFact,
    SuspiciousFormulaReason,
    UnknownMathFact,
    UnknownReason,
)
from scieqlint.facts.snapshot import FactSnapshot

_ENV_RE = re.compile(r"\\begin\{(?P<env>align\*?|gather\*?|multline\*?)\}")
_MACRO_RE = re.compile(r"\\(newcommand|renewcommand|DeclareMathOperator)\b")
_UNSUPPORTED_OPERATOR_RE = re.compile(r"\\(underset|overset|stackrel)\b")
_FORMULA_PLACEHOLDER_RE = re.compile(
    r"<!--\s*formula-(?:not-)?(?:decoded|recognized|available)\s*-->|"
    r"\[(?:FORMULA|MATH)(?:[_ -](?:NOT[_ -])?(?:DECODED|RECOGNIZED))?\]",
    re.IGNORECASE,
)
_GARBLED_MARKER_RE = re.compile(r"(?:cid:\d+|\\u[0-9A-Fa-f]{4}|\ufffd|�)")
_SPACED_TOKEN_RE = re.compile(
    r"\b[A-Za-z]\b(?:[\s,(){}\[\].;:+\-*/=<>|]+(?:\b[A-Za-z]\b|[A-Za-z]{2,})){5,}"
    r"[\s,(){}\[\].;:+\-*/=<>|]*"
)


class MathHost:
    """Own math classification and ``UnknownMath`` production."""

    def classify(self, snapshot: FactSnapshot) -> FactSnapshot:
        math_facts = (*snapshot.display_math, *snapshot.inline_math)
        unknown = tuple(_unknown_for_math(math_facts))
        suspicious = tuple(_suspicious_for_math(math_facts))
        return snapshot.with_unknown_math(unknown).with_suspicious_formulas(suspicious)


def _unknown_for_math(
    math_facts: Iterable[DisplayMathFact | InlineMathFact],
) -> Iterable[UnknownMathFact]:
    for fact in math_facts:
        result = _classify_unknown(fact.body)
        if result is None:
            continue
        reason, excerpt = result
        yield UnknownMathFact(
            fact_id=f"{fact.fact_id}::unknown::{reason}",
            document_id=fact.document_id,
            span=fact.span,
            raw=fact.raw,
            source_math_fact_id=fact.fact_id,
            reason=reason,
            excerpt=excerpt,
        )


def _classify_unknown(body: str) -> tuple[UnknownReason, str] | None:
    env_match = _ENV_RE.search(body)
    if env_match:
        return "environment", env_match.group(0)

    macro_match = _MACRO_RE.search(body)
    if macro_match:
        return "macro", macro_match.group(0)

    operator_match = _UNSUPPORTED_OPERATOR_RE.search(body)
    if operator_match:
        return cast(UnknownReason, "unsupported_operator"), operator_match.group(0)

    return None


def _suspicious_for_math(
    math_facts: Iterable[DisplayMathFact | InlineMathFact],
) -> Iterable[SuspiciousFormulaFact]:
    for fact in math_facts:
        result = _classify_suspicious_formula(fact.body)
        if result is None:
            continue
        reason, excerpt = result
        yield SuspiciousFormulaFact(
            fact_id=f"{fact.fact_id}::suspicious::{reason}",
            document_id=fact.document_id,
            span=fact.span,
            raw=fact.raw,
            source_math_fact_id=fact.fact_id,
            reason=reason,
            excerpt=excerpt,
        )


def _classify_suspicious_formula(body: str) -> tuple[SuspiciousFormulaReason, str] | None:
    placeholder = _FORMULA_PLACEHOLDER_RE.search(body)
    if placeholder:
        return "formula_placeholder", placeholder.group(0)

    garbled = _GARBLED_MARKER_RE.search(body)
    if garbled:
        return "garbled_marker", garbled.group(0)

    spaced = _SPACED_TOKEN_RE.search(body)
    if spaced and _single_letter_token_count(spaced.group(0)) >= 6:
        return "spaced_latex_tokens", spaced.group(0)

    return None


def _single_letter_token_count(value: str) -> int:
    return len(re.findall(r"\b[A-Za-z]\b", value))
