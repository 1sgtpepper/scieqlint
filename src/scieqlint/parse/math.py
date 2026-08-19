"""MathHost classification for frontend-produced inline math candidates."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace

from scieqlint.facts.generated import GeneratedFormulaFact, GeneratedFormulaKind
from scieqlint.facts.math import (
    DisplayMathFact,
    InlineMathFact,
    InlineParseStatus,
    UnknownMathFact,
    UnknownReason,
)
from scieqlint.facts.reference import EquationLabelFact, EquationRefFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.source.maps import SourceMap

_UNSUPPORTED_ENVIRONMENT_RE = re.compile(r"(?<!\\)\\(?:begin|end)\{(?P<environment>[A-Za-z]+\*?)\}")
_MISSING_BRACED_ARGUMENT_RE = re.compile(r"\\(?:frac|dfrac|tfrac|binom)\s*\{[^{}]*\}\s*$")
_TRAILING_OPERATOR_RE = re.compile(r"(?:[+\-*/^=]|<=|>=|<|>|\\(?:le|ge))\s*$")
_RELATION_RE = re.compile(r"(?:=|<=|>=|<|>|≤|≥|→)")
_OPENING_DELIMITERS = {"(": ")", "[": "]", "{": "}"}
_CLOSING_DELIMITERS = {value: key for key, value in _OPENING_DELIMITERS.items()}
_SPACED_COMMAND_RE = re.compile(
    r"(?P<artifact>\\[ \t]*(?:[A-Za-z][ \t]+){3,}[A-Za-z](?=[ \t]*[\[{]))"
)
_GARBLED_MARKER_RE = re.compile(r"(?<![A-Za-z0-9_])(?P<artifact>/C0[ \t]+apod)(?![A-Za-z0-9_])")
_AMS_ENVIRONMENTS = frozenset({"align", "align*", "aligned", "alignedat", "split"})
_AMS_BEGIN_RE = re.compile(r"\\begin\{(?P<environment>[A-Za-z]+\*?)\}")
_SUPPORTED_RAW_ENVIRONMENTS = frozenset(
    {
        "align",
        "align*",
        "equation",
        "equation*",
        "gather",
        "gather*",
        "multline",
        "multline*",
    }
)
_RAW_MATH_ENVIRONMENTS = frozenset(
    {
        *_SUPPORTED_RAW_ENVIRONMENTS,
        "aligned",
        "alignedat",
        "split",
        "cases",
        "array",
        "matrix",
        "pmatrix",
        "bmatrix",
        "Bmatrix",
        "vmatrix",
        "Vmatrix",
        "smallmatrix",
        "gathered",
        "multlined",
    }
)
_TEX_LABEL_RE = re.compile(r"\\label\{(?P<label>[^{}]+)\}")
_TEX_REFERENCE_RE = re.compile(r"\\(?P<kind>eqref|ref)\{(?P<target>[^{}\r\n]+)\}")


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
        display_math: list[DisplayMathFact] = []
        equation_labels = list(snapshot.equation_labels)
        equation_refs = list(snapshot.equation_refs)
        dropped_display_ids: set[str] = set()
        source_maps = {
            document.path.as_posix(): SourceMap.for_document(document)
            for document in snapshot.documents
        }
        for fact in snapshot.display_math:
            if fact.container == "raw-latex" and fact.environment not in _RAW_MATH_ENVIRONMENTS:
                dropped_display_ids.add(fact.fact_id)
                continue
            display, unknown = _classify_display(fact)
            if fact.container == "raw-latex":
                source_map = source_maps.get(fact.document_id)
                if source_map is not None:
                    labels, references = _raw_equation_facts(display, source_map)
                    display = replace(
                        display,
                        label_fact_ids=tuple(label.fact_id for label in labels),
                    )
                    equation_labels.extend(labels)
                    equation_refs.extend(references)
            display_math.append(display)
            if unknown is not None and fact.fact_id not in existing_unknown_ids:
                unknown_math.append(unknown)
        return replace(
            snapshot,
            inline_math=tuple(inline_math),
            display_math=tuple(display_math),
            equation_labels=tuple(equation_labels),
            equation_refs=tuple(equation_refs),
            unknown_math=(*snapshot.unknown_math, *unknown_math),
            generated_formulas=tuple(
                formula
                for formula in _classify_generated_formulas(snapshot)
                if formula.source_math_fact_id not in dropped_display_ids
            ),
        )


def _classify_display(
    fact: DisplayMathFact,
) -> tuple[DisplayMathFact, UnknownMathFact | None]:
    """Resolve AMS semantics after the frontend has preserved display identity."""

    if fact.container == "raw-latex":
        environment = fact.environment
        if environment not in _SUPPORTED_RAW_ENVIRONMENTS:
            return fact, _unknown(fact, "environment", environment or "<missing>")
        if not fact.complete:
            return fact, _unknown(fact, "parse_limit", environment)
        return replace(fact, container="ams"), None

    environment = _complete_ams_environment(fact.body)
    if environment is None:
        return fact, None
    return replace(fact, container="ams", environment=environment), None


def _raw_equation_facts(
    fact: DisplayMathFact,
    source_map: SourceMap,
) -> tuple[tuple[EquationLabelFact, ...], tuple[EquationRefFact, ...]]:
    """Materialize equation semantics from a classified raw math candidate."""

    if fact.span is None:
        return (), ()
    raw = fact.raw or ""
    labels: list[EquationLabelFact] = []
    references: list[EquationRefFact] = []
    for match in _TEX_LABEL_RE.finditer(raw):
        if _is_escaped(raw, match.start()):
            continue
        label = match.group("label")
        label_start = fact.span.start + match.start("label")
        labels.append(
            EquationLabelFact(
                fact_id=f"{fact.fact_id}::label::{label_start}",
                document_id=fact.document_id,
                span=source_map.span(label_start, label_start + len(label)),
                raw=label,
                label=label,
                normalized_label=_normalize_label(label),
                label_syntax_kind="tex-label",
                source_block_id=fact.fact_id,
                label_span=source_map.span(label_start, label_start + len(label)),
            )
        )
    for match in _TEX_REFERENCE_RE.finditer(raw):
        if _is_escaped(raw, match.start()):
            continue
        raw_target = match.group("target")
        target = raw_target.strip()
        if not target:
            continue
        leading = len(raw_target) - len(raw_target.lstrip())
        target_start = fact.span.start + match.start("target") + leading
        role_start = fact.span.start + match.start()
        role_end = fact.span.start + match.end()
        references.append(
            EquationRefFact(
                fact_id=f"{fact.fact_id}::ref::{target_start}",
                document_id=fact.document_id,
                span=source_map.span(role_start, role_end),
                raw=match.group(0),
                ref_kind=f"tex-{match.group('kind')}",
                target=target,
                normalized_target=_normalize_label(target),
                source_block_id=fact.fact_id,
                role_span=source_map.span(role_start, role_end),
                target_span=source_map.span(target_start, target_start + len(target)),
            )
        )
    return tuple(labels), tuple(references)


def _normalize_label(value: str) -> str:
    value = value.strip()
    return value[1:] if value.startswith("#") else value


def _complete_ams_environment(body: str) -> str | None:
    for match in _AMS_BEGIN_RE.finditer(body):
        environment = match.group("environment")
        if environment not in _AMS_ENVIRONMENTS or _is_escaped(body, match.start()):
            continue
        end_pattern = re.compile(rf"\\end\{{{re.escape(environment)}\}}")
        if any(
            not _is_escaped(body, end_match.start())
            for end_match in end_pattern.finditer(body, match.end())
        ):
            return environment
    return None


def _is_escaped(text: str, offset: int) -> bool:
    backslashes = 0
    cursor = offset - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _classify_inline(
    fact: InlineMathFact,
) -> tuple[InlineParseStatus, UnknownMathFact | None]:
    if fact.delimiter_kind == "plain-text":
        if _looks_like_plain_text_math(fact.body):
            return "text-leak", None
        return "not-math", None

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


def _classify_generated_formulas(snapshot: FactSnapshot) -> tuple[GeneratedFormulaFact, ...]:
    source_maps = {
        document.path.as_posix(): SourceMap.for_document(document)
        for document in snapshot.documents
    }
    facts: list[GeneratedFormulaFact] = []
    for candidate in snapshot.generated_formulas:
        if candidate.kind != "candidate":
            facts.append(candidate)
            continue
        source_map = source_maps.get(candidate.document_id)
        if source_map is None or candidate.span is None:
            continue
        facts.extend(_classify_generated_candidate(candidate, source_map))
    return tuple(
        sorted(
            facts,
            key=lambda fact: (fact.span.start if fact.span is not None else -1, fact.fact_id),
        )
    )


def _classify_generated_candidate(
    candidate: GeneratedFormulaFact,
    source_map: SourceMap,
) -> tuple[GeneratedFormulaFact, ...]:
    if candidate.candidate_kind in {None, "formula-text"}:
        return _suspicious_formula_facts(candidate, source_map)
    if candidate.candidate_kind == "bracketed-block":
        return (replace(candidate, kind="bracketed-block", candidate_kind=None),)
    if candidate.candidate_kind == "placeholder":
        kind = (
            "empty-display"
            if candidate.placeholder_kind == "empty-display-math"
            else "image-placeholder"
            if candidate.placeholder_kind == "formula-image"
            else "placeholder"
        )
        return (replace(candidate, kind=kind, candidate_kind=None),)
    if candidate.candidate_kind == "equation-like-text":
        if not _has_high_confidence_math_signal(candidate.text):
            return ()
        return (
            replace(
                candidate,
                kind="equation-like-text",
                candidate_kind=None,
                confidence="inferred",
            ),
        )
    raise ValueError(f"unsupported generated formula candidate kind: {candidate.candidate_kind}")


def _suspicious_formula_facts(
    candidate: GeneratedFormulaFact,
    source_map: SourceMap,
) -> tuple[GeneratedFormulaFact, ...]:
    assert candidate.span is not None
    patterns: tuple[tuple[GeneratedFormulaKind, re.Pattern[str], Callable[[str], bool]], ...] = (
        ("spaced-token", _SPACED_COMMAND_RE, _high_confidence_spaced_command),
        ("garbled-marker", _GARBLED_MARKER_RE, _always_accept),
    )
    facts: list[GeneratedFormulaFact] = []
    occupied: list[tuple[int, int]] = []
    for kind, pattern, accept in patterns:
        for match in pattern.finditer(candidate.text):
            artifact = match.group("artifact")
            if not accept(artifact):
                continue
            local_start, local_end = match.span("artifact")
            start = candidate.span.start + local_start
            end = candidate.span.start + local_end
            if any(
                start < occupied_end and occupied_start < end
                for occupied_start, occupied_end in occupied
            ):
                continue
            occupied.append((start, end))
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


def _has_high_confidence_math_signal(text: str) -> bool:
    if any(character.isdigit() for character in text):
        return True
    if any(character in text for character in r"\_^{}*/+()[]"):
        return True
    words = re.findall(r"(?<!\\)[A-Za-z]+", text)
    return bool(words) and all(len(word) <= 3 for word in words)


def _high_confidence_spaced_command(artifact: str) -> bool:
    letters = re.findall(r"[A-Za-z]", artifact)
    return len(letters) >= 4 and sum(letter.islower() for letter in letters) >= 2


def _always_accept(_artifact: str) -> bool:
    return True
