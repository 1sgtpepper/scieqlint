"""Architecture DiagnosticIR."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.diag.model import Diagnostic, Severity, SourceSpan


@dataclass(frozen=True, slots=True)
class RelatedLocation:
    span: SourceSpan
    message: str


@dataclass(frozen=True, slots=True)
class DiagnosticIR:
    code: str
    message: str
    span: SourceSpan | None
    severity_default: Severity
    detail: str | None = None
    hint: str | None = None
    rule: str | None = None
    profile_gated: bool = False
    false_positive_risk: str | None = None
    related_locations: tuple[RelatedLocation, ...] = ()
    profile: str | None = None
    provenance_ids: tuple[str, ...] = ()
    properties: tuple[tuple[str, str], ...] = ()

    def to_diagnostic(self, severity: Severity | None = None) -> Diagnostic:
        return Diagnostic(
            code=self.code,
            severity=severity or self.severity_default,
            message=self.message,
            span=self.span,
            detail=self.detail,
            hint=self.hint,
            rule=self.rule,
            profile=self.profile,
            provenance_ids=self.provenance_ids,
            properties=self.properties,
        )
