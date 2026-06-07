"""Parser result contracts for the supported v0.1.0 subset."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.diag.model import Diagnostic
from scieqlint.parse.ast import EquationGroup


@dataclass(frozen=True, slots=True)
class ParseOk:
    ast: EquationGroup


@dataclass(frozen=True, slots=True)
class ParseUnknown:
    reason: str
    diagnostics: tuple[Diagnostic, ...]
