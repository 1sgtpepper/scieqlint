"""MathHost classification for frontend-produced inline math candidates."""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import replace

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.generated import GeneratedFormulaFact, GeneratedFormulaKind
from scieqlint.facts.math import (
    DisplayMathFact,
    InlineMathFact,
    InlineParseStatus,
    MathMacroDeclarationFact,
    MathMacroUseFact,
    UnknownMathFact,
    UnknownReason,
)
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.reference import EquationLabelFact, EquationRefFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.io.source import SourceDocument
from scieqlint.markdown import (
    is_escaped,
    is_non_math_tex_environment,
    range_contains,
    scan_tex_lexically,
    without_tex_comments,
)
from scieqlint.source.maps import SourceMap

from .macros import (
    InlineMacroSource,
    MacroDeclarationKey,
    scan_scoped_inline_macros,
)

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
_TEX_LABEL_RE = re.compile(r"\\label\{(?P<label>[^{}\r\n]+)\}")
_TEX_REFERENCE_RE = re.compile(r"\\(?P<kind>eqref|ref)\{(?P<target>[^{}\r\n]+)\}")
_TYPST_UNSUPPORTED_COMMAND_RE = re.compile(r"\\(?P<command>dfrac|argmin)(?![A-Za-z])")
_TYPST_DELIMITER_RE = re.compile(r"\\(?P<delimiter>left|right)(?![A-Za-z])")


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
        existing_label_ids = {fact.fact_id for fact in equation_labels}
        existing_ref_ids = {fact.fact_id for fact in equation_refs}
        raw_display_ids = {
            fact.fact_id for fact in snapshot.display_math if fact.container == "raw-latex"
        }
        source_maps = {
            document.path.as_posix(): SourceMap.for_document(document)
            for document in snapshot.documents
        }
        for fact in snapshot.display_math:
            if fact.container == "raw-latex" and is_non_math_tex_environment(fact.environment):
                continue
            display, unknown = _classify_display(fact)
            if (
                fact.container == "raw-latex"
                and fact.complete
                and not is_non_math_tex_environment(fact.environment)
            ):
                labels, references = _raw_equation_facts(
                    display,
                    source_maps[fact.document_id],
                )
                display = replace(
                    display,
                    label_fact_ids=tuple(label.fact_id for label in labels),
                )
                for label in labels:
                    if label.fact_id in existing_label_ids:
                        continue
                    equation_labels.append(label)
                    existing_label_ids.add(label.fact_id)
                for reference in references:
                    if reference.fact_id in existing_ref_ids:
                        continue
                    equation_refs.append(reference)
                    existing_ref_ids.add(reference.fact_id)
            display_math.append(display)
            if unknown is not None and fact.fact_id not in existing_unknown_ids:
                unknown_math.append(unknown)
        macro_declarations, macro_uses = inline_math_macro_facts(
            snapshot.documents,
            tuple(inline_math),
        )
        classified = replace(
            snapshot,
            inline_math=tuple(inline_math),
            display_math=tuple(display_math),
            equation_labels=tuple(equation_labels),
            equation_refs=tuple(equation_refs),
            math_macro_declarations=macro_declarations,
            math_macro_uses=macro_uses,
            unknown_math=(*snapshot.unknown_math, *unknown_math),
        )
        accepted_raw_display_ids = {
            fact.fact_id
            for fact in display_math
            if fact.fact_id in raw_display_ids and fact.container == "ams"
        }
        return replace(
            classified,
            generated_formulas=tuple(
                formula
                for formula in _classify_generated_formulas(classified)
                if not (
                    formula.source_math_fact_id in raw_display_ids
                    and formula.source_math_fact_id not in accepted_raw_display_ids
                )
            ),
        )

    def typst_portability(
        self,
        snapshot: FactSnapshot,
    ) -> tuple[OutputPortabilityFact, ...]:
        """Classify source math forms whose semantics need Typst review."""

        return _typst_math_risks(snapshot)


def _classify_display(
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


def _raw_equation_facts(
    fact: DisplayMathFact,
    source_map: SourceMap,
) -> tuple[tuple[EquationLabelFact, ...], tuple[EquationRefFact, ...]]:
    """Materialize facts from a complete raw candidate outside opaque containers."""

    assert fact.span is not None, "raw-LaTeX candidates must retain source spans"
    raw = fact.raw or ""
    lexical = scan_tex_lexically(raw)
    active_raw = lexical.active_text
    opaque_ranges = lexical.non_math_ranges
    line_starts = _splitline_starts(raw) if fact.span.cell_line is not None else ()
    labels: list[EquationLabelFact] = []
    references: list[EquationRefFact] = []
    for match in _TEX_LABEL_RE.finditer(active_raw):
        if is_escaped(raw, match.start()) or range_contains(match.start(), opaque_ranges):
            continue
        label = match.group("label")
        if not label.strip():
            continue
        label_start = match.start("label")
        label_span = _raw_subspan(
            fact,
            source_map,
            label_start,
            label_start + len(label),
            line_starts,
        )
        labels.append(
            EquationLabelFact(
                fact_id=(
                    f"{fact.fact_id}::label::"
                    f"{label_start if fact.span.segments else label_span.start}"
                ),
                document_id=fact.document_id,
                span=label_span,
                raw=label,
                label=label,
                normalized_label=_normalize_label(label),
                label_syntax_kind="tex-label",
                source_block_id=fact.fact_id,
                label_span=label_span,
            )
        )
    for match in _TEX_REFERENCE_RE.finditer(active_raw):
        if is_escaped(raw, match.start()) or range_contains(match.start(), opaque_ranges):
            continue
        raw_target = match.group("target")
        target = raw_target.strip()
        if not target:
            continue
        leading = len(raw_target) - len(raw_target.lstrip())
        target_start = match.start("target") + leading
        role_start = match.start()
        role_end = match.end()
        role_span = _raw_subspan(fact, source_map, role_start, role_end, line_starts)
        target_span = _raw_subspan(
            fact,
            source_map,
            target_start,
            target_start + len(target),
            line_starts,
        )
        references.append(
            EquationRefFact(
                fact_id=(
                    f"{fact.fact_id}::ref::"
                    f"{target_start if fact.span.segments else target_span.start}"
                ),
                document_id=fact.document_id,
                span=role_span,
                raw=match.group(0),
                ref_kind=f"tex-{match.group('kind')}",
                target=target,
                normalized_target=_normalize_label(target),
                source_block_id=fact.fact_id,
                role_span=role_span,
                target_span=target_span,
            )
        )
    return tuple(labels), tuple(references)


def _raw_subspan(
    fact: DisplayMathFact,
    source_map: SourceMap,
    start: int,
    end: int,
    line_starts: tuple[int, ...],
) -> SourceSpan:
    """Map a raw-equation subspan without reconstructing notebook source text."""

    assert fact.span is not None, "raw-LaTeX candidates must retain source spans"
    raw = fact.raw or ""
    if start < 0 or end <= start or end > len(raw):
        raise ValueError("raw equation subspan is outside its source text")
    cell_line = (
        None
        if fact.span.cell_line is None
        else fact.span.cell_line + bisect_right(line_starts, start) - 1
    )
    if fact.span.segments:
        if len(fact.span.segments) != len(raw):
            raise ValueError("raw equation source mapping does not match its source text")
        segments = fact.span.segments[start:end]
        first = segments[0]
        last = segments[-1]
        return replace(
            fact.span,
            start=first.start,
            end=last.end,
            line=first.line,
            col=first.col,
            end_line=last.end_line,
            end_col=last.end_col,
            cell_line=cell_line,
            segments=segments,
        )
    mapped = source_map.span(fact.span.start + start, fact.span.start + end)
    return replace(
        mapped,
        cell=fact.span.cell,
        cell_line=cell_line,
    )


def _splitline_starts(text: str) -> tuple[int, ...]:
    """Index Python split-line boundaries once for repeated local span mapping."""

    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return tuple(starts)


def _normalize_label(value: str) -> str:
    value = value.strip()
    return value[1:] if value.startswith("#") else value


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
    line_starts = _splitline_starts(candidate.text) if candidate.span.cell_line is not None else ()
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
            artifact_span = source_map.span(start, end)
            fact_id = f"{candidate.document_id}::generated-formula::{kind}::{start}"
            if candidate.span.segments:
                if len(candidate.span.segments) != len(candidate.text):
                    raise ValueError(
                        "generated formula source mapping does not match its source text"
                    )
                segments = candidate.span.segments[local_start:local_end]
                first = segments[0]
                last = segments[-1]
                artifact_span = replace(
                    candidate.span,
                    start=first.start,
                    end=last.end,
                    line=first.line,
                    col=first.col,
                    end_line=last.end_line,
                    end_col=last.end_col,
                    cell_line=(
                        None
                        if candidate.span.cell_line is None
                        else candidate.span.cell_line + bisect_right(line_starts, local_start) - 1
                    ),
                    segments=segments,
                )
                fact_id = f"{candidate.fact_id}::{kind}::{local_start}"
            facts.append(
                GeneratedFormulaFact(
                    fact_id=fact_id,
                    document_id=candidate.document_id,
                    span=artifact_span,
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


def inline_math_macro_facts(
    documents: Sequence[SourceDocument],
    inline_math: Sequence[InlineMathFact],
) -> tuple[tuple[MathMacroDeclarationFact, ...], tuple[MathMacroUseFact, ...]]:
    """Resolve macro declarations and uses after MathHost owns math candidates."""

    documents_by_id = {document.path.as_posix(): document for document in documents}
    source_maps = {
        document_id: SourceMap.for_document(document)
        for document_id, document in documents_by_id.items()
    }
    facts_by_id: dict[str, InlineMathFact] = {}
    sources: list[InlineMacroSource] = []
    for fact in inline_math:
        if (
            fact.delimiter_kind == "plain-text"
            or fact.confidence != "source"
            or fact.span is None
            or fact.document_id not in documents_by_id
        ):
            continue
        document = documents_by_id[fact.document_id]
        segments = fact.span.segments
        if not segments:
            if document.text[fact.span.start : fact.span.end] != fact.body:
                continue
        else:
            if (
                len(segments) != len(fact.body)
                or fact.span.start != segments[0].start
                or fact.span.end != segments[-1].end
            ):
                continue
            previous_end = -1
            valid_segments = True
            for segment in segments:
                for range_start, range_end in segment.ranges:
                    if (
                        range_start < previous_end
                        or range_start < 0
                        or range_end > len(document.text)
                    ):
                        valid_segments = False
                        break
                    previous_end = range_end
                if not valid_segments:
                    break
            if not valid_segments:
                continue
        facts_by_id[fact.fact_id] = fact
        sources.append(
            InlineMacroSource(
                document_id=fact.document_id,
                source_fact_id=fact.fact_id,
                source_start=fact.span.start,
                body=fact.body,
            )
        )

    scoped = scan_scoped_inline_macros(tuple(sources))
    line_starts_by_fact_id: dict[str, tuple[int, ...]] = {}

    def line_starts(fact: InlineMathFact) -> tuple[int, ...]:
        assert fact.span is not None
        if fact.span.cell_line is None:
            return ()
        starts = line_starts_by_fact_id.get(fact.fact_id)
        if starts is None:
            starts = _splitline_starts(fact.body)
            line_starts_by_fact_id[fact.fact_id] = starts
        return starts

    declarations: list[MathMacroDeclarationFact] = []
    declaration_ids: dict[MacroDeclarationKey, str] = {}
    for item in scoped.declarations:
        fact = facts_by_id[item.source.source_fact_id]
        assert fact.span is not None
        syntax = item.declaration
        fact_id = f"{fact.fact_id}::macro-declaration::{syntax.start}"
        declaration_ids[MacroDeclarationKey(fact.fact_id, syntax.start)] = fact_id
        declarations.append(
            MathMacroDeclarationFact(
                fact_id=fact_id,
                document_id=fact.document_id,
                span=_inline_macro_span(
                    fact,
                    source_maps[fact.document_id],
                    syntax.name_start,
                    syntax.name_end,
                    line_starts(fact),
                ),
                raw=fact.body[syntax.start : syntax.end],
                source_math_fact_id=fact.fact_id,
                macro_name=syntax.name,
                declaration_kind=syntax.declaration_kind,
                parameter_count=syntax.parameter_count,
                replacement=syntax.replacement,
                declaration_order=item.declaration_order,
            )
        )

    uses: list[MathMacroUseFact] = []
    for item in scoped.uses:
        fact = facts_by_id[item.source.source_fact_id]
        assert fact.span is not None
        syntax = item.use
        uses.append(
            MathMacroUseFact(
                fact_id=f"{fact.fact_id}::macro-use::{syntax.start}",
                document_id=fact.document_id,
                span=_inline_macro_span(
                    fact,
                    source_maps[fact.document_id],
                    syntax.start,
                    syntax.end,
                    line_starts(fact),
                ),
                raw=fact.body[syntax.start : syntax.end],
                source_math_fact_id=fact.fact_id,
                macro_name=syntax.name,
                active_declaration_fact_id=(
                    declaration_ids[item.active_declaration]
                    if item.active_declaration is not None
                    else None
                ),
            )
        )
    return tuple(declarations), tuple(uses)


def _inline_macro_span(
    fact: InlineMathFact,
    source_map: SourceMap,
    start: int,
    end: int,
    line_starts: tuple[int, ...],
) -> SourceSpan:
    assert fact.span is not None
    # Macro scanner offsets are bounded by ``fact.body``.
    if start < 0 or end <= start or end > len(fact.body):  # pragma: no cover
        raise ValueError("inline macro subspan is outside its source text")
    cell_line = (
        None
        if fact.span.cell_line is None
        else fact.span.cell_line + bisect_right(line_starts, start) - 1
    )
    if fact.span.segments:
        # Mapped facts are length-validated before scanner admission.
        if len(fact.span.segments) != len(fact.body):  # pragma: no cover
            raise ValueError("inline macro source mapping does not match its source text")
        segments = fact.span.segments[start:end]
        first = segments[0]
        last = segments[-1]
        return replace(
            fact.span,
            start=first.start,
            end=last.end,
            line=first.line,
            col=first.col,
            end_line=last.end_line,
            end_col=last.end_col,
            cell_line=cell_line,
            segments=segments,
        )
    span = source_map.span(fact.span.start + start, fact.span.start + end)
    return replace(
        span,
        cell=fact.span.cell,
        cell_line=cell_line,
    )


def _typst_math_risks(
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
