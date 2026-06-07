"""Reporter protocol."""

from __future__ import annotations

from typing import Protocol

from scieqlint.diag.model import CheckResult


class Reporter(Protocol):
    def render(self, result: CheckResult) -> str: ...
