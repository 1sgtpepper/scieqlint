"""Profile definitions for architecture-owned engines."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.diag.model import Severity


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    engines: frozenset[str]
    rules: frozenset[str]
    severities: tuple[tuple[str, Severity], ...] = ()

    def severity_map(self) -> dict[str, Severity]:
        return dict(self.severities)


_DEFAULT_RULES = frozenset({"STR002", "REF010", "REF011", "REF012", "MATH020"})
_MYST_RULES = frozenset(
    {
        "STR001",
        "STR002",
        "STR003",
        "STR004",
        "DIR010",
        "REF001",
        "REF002",
        "REF010",
        "REF011",
        "REF012",
        "REF013",
        "MATH020",
        "MATH021",
    }
)
_GENERATED_RULES = _MYST_RULES | frozenset(
    {"REF014", "GEN002", "GEN003", "GEN004", "GEN005", "GEN006"}
)
_PORTABILITY_RULES = frozenset({"PORT001", "PORT002", "MATH020", "MATH021"})
_QUARTO_RULES = frozenset({"PROJ002", "PORT003", "PORT004", "MATH021"})

PROFILES: dict[str, Profile] = {
    "default": Profile(
        name="default",
        engines=frozenset({"structure", "references", "math-container"}),
        rules=_DEFAULT_RULES,
    ),
    "scientific-myst": Profile(
        name="scientific-myst",
        engines=frozenset({"structure", "references", "math-container"}),
        rules=_MYST_RULES,
    ),
    "generated": Profile(
        name="generated",
        engines=frozenset({"structure", "references", "math-container", "generated"}),
        rules=_GENERATED_RULES,
        severities=(("REF011", Severity.ERROR),),
    ),
    "portability-typst": Profile(
        name="portability-typst",
        engines=frozenset({"portability", "math-container"}),
        rules=_PORTABILITY_RULES,
    ),
    "quarto-project": Profile(
        name="quarto-project",
        engines=frozenset({"project", "portability", "math-container"}),
        rules=_QUARTO_RULES,
    ),
    "strict-ci": Profile(
        name="strict-ci",
        engines=frozenset(),
        rules=frozenset(),
        severities=(
            ("STR001", Severity.ERROR),
            ("STR002", Severity.ERROR),
            ("REF011", Severity.ERROR),
            ("MATH020", Severity.ERROR),
        ),
    ),
}
