"""MathHost: classify math facts and produce ``UnknownMath`` facts."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import cast

from scieqlint.facts.math import (
    DisplayMathFact,
    InlineMathFact,
    UnknownMathFact,
    UnknownReason,
)
from scieqlint.facts.snapshot import FactSnapshot

_ENV_RE = re.compile(r"\\begin\{(?P<env>align\*?|gather\*?|multline\*?)\}")
_MACRO_RE = re.compile(r"\\(newcommand|renewcommand|DeclareMathOperator)\b")
_UNSUPPORTED_OPERATOR_RE = re.compile(r"\\(underset|overset|stackrel)\b")


class MathHost:
    """Own math classification and ``UnknownMath`` production."""

    def classify(self, snapshot: FactSnapshot) -> FactSnapshot:
        unknown = tuple(_unknown_for_math((*snapshot.display_math, *snapshot.inline_math)))
        return snapshot.with_unknown_math(unknown)


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
