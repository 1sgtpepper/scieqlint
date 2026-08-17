"""Fact-only output portability classification.

The helpers in this module project already-lowered semantic facts into explicit
portability risks.  They do not emit diagnostics and never inspect reporter
output.
"""

from __future__ import annotations

import re

from scieqlint.facts.math import DisplayMathFact
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.reference import EquationRefFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.markdown import is_escaped
from scieqlint.source.maps import SourceMap

_REFERENCE_SUPPORT: dict[str, frozenset[str]] = {
    # CommonMark and plain notebook Markdown have no native equation-reference
    # contract.  A downstream extension may support one, but the configured
    # profile deliberately models the portable baseline.
    "commonmark": frozenset(),
    "notebook": frozenset(),
    # MyST owns the role forms and preserves TeX commands inside math.
    "myst": frozenset({"eq", "numref", "tex-ref", "tex-eqref"}),
    # Typst publishing paths can lower semantic MyST equation roles, while raw
    # TeX reference commands are output-profile-specific source syntax.
    "typst": frozenset({"eq", "numref"}),
}

_TYPST_UNSUPPORTED_COMMAND_RE = re.compile(r"\\(?P<command>dfrac|argmin)(?![A-Za-z])")
_TYPST_DELIMITER_RE = re.compile(r"\\(?P<delimiter>left|right)(?![A-Za-z])")
_TYPST_FRAGILE_ENVIRONMENT_RE = re.compile(r"\\begin\{(?P<environment>aligned|array|matrix)\}")


def cross_format_reference_risks(
    snapshot: FactSnapshot,
    output_profile: str,
) -> tuple[OutputPortabilityFact, ...]:
    """Return equation-reference syntax risks for an explicit output profile."""

    supported = _REFERENCE_SUPPORT[output_profile]
    return tuple(
        _reference_risk(reference, output_profile)
        for reference in snapshot.equation_refs
        if reference.ref_kind not in supported
    )


def _reference_risk(
    reference: EquationRefFact,
    output_profile: str,
) -> OutputPortabilityFact:
    return OutputPortabilityFact(
        fact_id=f"{reference.fact_id}::portability::{output_profile}",
        document_id=reference.document_id,
        span=reference.role_span or reference.span,
        raw=reference.raw,
        confidence=reference.confidence,
        subject_fact_id=reference.fact_id,
        output_profile=output_profile,
        risk_kind="equation-reference-syntax",
        metadata=(
            ("ref_kind", reference.ref_kind),
            ("target", reference.target),
        ),
    )


def typst_math_risks(snapshot: FactSnapshot) -> tuple[OutputPortabilityFact, ...]:
    """Return focused, source-spanned risks for Typst display-math export."""

    documents = {document.path.as_posix(): document for document in snapshot.documents}
    risks: list[OutputPortabilityFact] = []
    for display in snapshot.display_math:
        if display.span is None:
            continue
        document = documents.get(display.document_id)
        if document is None:
            continue
        segment = document.text[display.span.start : display.span.end]
        smap = SourceMap.for_document(document)
        risks.extend(_typst_command_risks(display, segment, smap))
        risks.extend(_typst_environment_risks(display, segment, smap))
    return tuple(
        sorted(
            risks,
            key=lambda fact: (
                fact.span.start if fact.span is not None else -1,
                fact.fact_id,
            ),
        )
    )


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
    smap: SourceMap,
) -> list[OutputPortabilityFact]:
    assert display.span is not None
    delimiters = tuple(
        dict.fromkeys(
            match.group("delimiter")
            for match in _TYPST_DELIMITER_RE.finditer(segment)
            if not is_escaped(segment, match.start())
        )
    )
    if not delimiters:
        return []

    risks: list[OutputPortabilityFact] = []
    for match in _TYPST_FRAGILE_ENVIRONMENT_RE.finditer(segment):
        if is_escaped(segment, match.start()):
            continue
        start = display.span.start + match.start()
        end = display.span.start + match.end()
        environment = match.group("environment")
        risks.append(
            OutputPortabilityFact(
                fact_id=f"{display.fact_id}::typst-environment::{start}",
                document_id=display.document_id,
                span=smap.span(start, end),
                raw=match.group(0),
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
