"""Output-profile policy owned outside frontends and diagnostic engines."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Severity
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.reference import EquationRefFact
from scieqlint.facts.snapshot import FactSnapshot

_REFERENCE_SUPPORT: dict[str, frozenset[str]] = {
    # CommonMark and plain notebook Markdown have no native equation-reference
    # contract. A downstream extension may support one, but the configured
    # profile deliberately models the portable baseline.
    "commonmark": frozenset(),
    "notebook": frozenset(),
    # MyST owns the role forms and preserves TeX commands inside math.
    "myst": frozenset({"eq", "numref", "tex-ref", "tex-eqref"}),
    # Typst publishing paths can lower semantic MyST equation roles, while raw
    # TeX reference commands are output-profile-specific source syntax.
    "typst": frozenset({"eq", "numref"}),
}


def _validated_output_profile(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"unsupported output profile: {value}")
    return value


@dataclass(frozen=True, slots=True)
class PolicyHost:
    """Resolve configured support and severity policy for fact consumers."""

    output_profile: str | None = None

    def severity(self, code: str) -> Severity:
        """Return the catalog severity selected for one diagnostic code."""

        return CATALOG[code].severity

    def cross_format_reference_risks(
        self,
        snapshot: FactSnapshot,
        output_profile: str | None = None,
    ) -> tuple[OutputPortabilityFact, ...]:
        """Project equation-reference facts into output-profile risks."""

        profile_value = self.output_profile if output_profile is None else output_profile
        if profile_value is None:
            raise ValueError("cross-format reference policy requires an output profile")
        profile = _validated_output_profile(profile_value)
        try:
            supported = _REFERENCE_SUPPORT[profile]
        except KeyError as exc:
            raise ValueError(f"unsupported output profile: {profile}") from exc
        return tuple(
            _reference_risk(reference, profile)
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
