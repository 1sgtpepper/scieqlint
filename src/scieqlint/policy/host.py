"""PolicyHost: plan before engines, apply after engines."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.diag.model import Diagnostic, Severity
from scieqlint.policy.profiles import PROFILES


@dataclass(frozen=True, slots=True)
class AnalysisPlan:
    profiles: tuple[str, ...]
    engines: frozenset[str]
    rules: frozenset[str]
    severity_overrides: tuple[tuple[str, Severity], ...]

    def severity_for(self, diagnostic: DiagnosticIR) -> Severity:
        return dict(self.severity_overrides).get(
            diagnostic.code,
            diagnostic.severity_default,
        )


class PolicyHost:
    """Own profiles, severities, suppressions, and baselines.

    This implementation includes the first two policy phases:

    1. ``make_plan()`` selects engines/rules before analysis.
    2. ``apply()`` filters and severity-maps ``DiagnosticIR`` after analysis.

    Existing suppressions and baselines can be wired into ``apply()`` during the
    compatibility PR that moves the stable CLI onto this pipeline.
    """

    def make_plan(self, profiles: tuple[str, ...] = ("default",)) -> AnalysisPlan:
        selected = profiles or ("default",)
        engines: set[str] = set()
        rules: set[str] = set()
        severities: dict[str, Severity] = {}
        for name in selected:
            profile = PROFILES.get(name)
            if profile is None:
                raise ValueError(f"unknown profile: {name}")
            engines.update(profile.engines)
            rules.update(profile.rules)
            severities.update(profile.severity_map())

        if "strict-ci" in selected and len(selected) == 1:
            default = PROFILES["default"]
            engines.update(default.engines)
            rules.update(default.rules)

        return AnalysisPlan(
            profiles=tuple(selected),
            engines=frozenset(engines),
            rules=frozenset(rules),
            severity_overrides=tuple(sorted(severities.items())),
        )

    def apply(
        self,
        diagnostics: tuple[DiagnosticIR, ...],
        plan: AnalysisPlan,
    ) -> tuple[Diagnostic, ...]:
        out: list[Diagnostic] = []
        for diagnostic in diagnostics:
            if plan.rules and diagnostic.code not in plan.rules:
                continue
            out.append(diagnostic.to_diagnostic(plan.severity_for(diagnostic)))
        return tuple(sorted(out, key=_diagnostic_key))


def _diagnostic_key(diagnostic: Diagnostic) -> tuple[str, int, int, str]:
    span = diagnostic.span
    if span is None:
        return ("", -1, -1, diagnostic.code)
    return (span.path.as_posix(), span.line, span.col, diagnostic.code)
