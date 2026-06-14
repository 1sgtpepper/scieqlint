"""SchemaHost-style architecture result projection."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.diag.model import Diagnostic
from scieqlint.facts.snapshot import FactSnapshot


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    snapshot: FactSnapshot
    diagnostics: tuple[Diagnostic, ...]
    profiles: tuple[str, ...]
    schema_version: str = "0.2-architecture-preview"

    def summary(self) -> dict[str, int]:
        return {
            "files_checked": len(self.snapshot.documents),
            "facts": len(self.snapshot.all_facts()),
            "diagnostics": len(self.diagnostics),
            "errors": sum(1 for d in self.diagnostics if d.severity.value == "error"),
            "warnings": sum(1 for d in self.diagnostics if d.severity.value == "warning"),
            "info": sum(1 for d in self.diagnostics if d.severity.value == "info"),
        }
