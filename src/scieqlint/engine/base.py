"""Engine base protocol."""

from __future__ import annotations

from typing import Protocol

from scieqlint.diag.ir import DiagnosticIR
from scieqlint.query.host import QueryHost


class Engine(Protocol):
    name: str
    rule_codes: frozenset[str]

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]: ...
