"""Fact-only output portability classification.

The helpers in this module project already-lowered semantic facts into explicit
portability risks.  They do not emit diagnostics and never inspect reporter
output.
"""

from __future__ import annotations

from scieqlint.config.model import OutputProfile
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.reference import EquationRefFact
from scieqlint.facts.snapshot import FactSnapshot

_REFERENCE_SUPPORT: dict[OutputProfile, frozenset[str]] = {
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


def cross_format_reference_risks(
    snapshot: FactSnapshot,
    output_profile: OutputProfile,
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
    output_profile: OutputProfile,
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
