"""Math facts and UnknownMath records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scieqlint.facts.base import FactBase

InlineDelimiter = Literal[
    "dollar",
    "myst-role",
    "quarto-inline",
    "latex-paren",
    "plain-text",
]
# Frontend candidates are classified by MathHost; ``not-math`` is retained for
# provenance but is excluded from the engine-facing math query.
InlineParseStatus = Literal[
    "candidate",
    "preserved",
    "not-math",
    "unsupported",
    "text-leak",
]
InlineTextRole = Literal["paragraph", "heading", "list-item", "blockquote"]
DisplayContainer = Literal[
    "dollar-dollar",
    "myst-math-directive",
    "fenced-math",
    "latex-display",
    "ams",
    "quarto-equation",
    "raw-latex",
]
MathMacroDeclarationKind = Literal[
    "newcommand",
    "renewcommand",
    "providecommand",
    "def",
]
UnknownReason = Literal[
    "unsupported_syntax",
    "unsupported_function",
    "unsupported_operator",
    "macro",
    "environment",
    "ambiguous_delimiter",
    "parse_limit",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class InlineMathFact(FactBase):
    body: str
    delimiter_kind: InlineDelimiter
    accessibility_id: str | None = None
    alt: str | None = None
    surrounding_text_role: InlineTextRole = "paragraph"
    parse_status: InlineParseStatus = "candidate"


@dataclass(frozen=True, slots=True, kw_only=True)
class DisplayMathFact(FactBase):
    body: str
    container: DisplayContainer
    # Source width of recognized directive options, excluded from TeX interpretation.
    option_prefix_length: int = 0
    # Equation labels and references use this enclosing display as their owner;
    # row-level equation-number identity is intentionally not modeled yet.
    label_fact_ids: tuple[str, ...] = ()
    alt: str | None = None
    enumerated: bool | None = None
    complete: bool = True
    environment: str | None = None
    source_syntax: Literal["raw-latex"] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class UnknownMathFact(FactBase):
    source_math_fact_id: str
    reason: UnknownReason
    excerpt: str
    classifier: str = "MathHost"


@dataclass(frozen=True, slots=True, kw_only=True)
class MathMacroDeclarationFact(FactBase):
    source_math_fact_id: str
    macro_name: str
    declaration_kind: MathMacroDeclarationKind
    parameter_count: int
    replacement: str
    declaration_order: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MathMacroUseFact(FactBase):
    source_math_fact_id: str
    macro_name: str
    active_declaration_fact_id: str | None
