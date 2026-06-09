"""Diagnostic data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    path: PurePosixPath
    start: int
    end: int
    line: int
    col: int
    end_line: int
    end_col: int
    cell: int | None = None
    cell_line: int | None = None


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: Severity
    message: str
    span: SourceSpan | None
    equation: str | None = None
    detail: str | None = None
    hint: str | None = None
    rule: str | None = None
    suppressed: bool = False
    suppression_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CheckResult:
    diagnostics: tuple[Diagnostic, ...]
    files_checked: int
    math_blocks_checked: int
    config_path: PurePosixPath | None
    version: str
    show_suppressed: bool = False

    def exit_code(self) -> int:
        """Return 1 only when an unsuppressed error diagnostic exists."""
        if any(d.severity is Severity.ERROR and not d.suppressed for d in self.diagnostics):
            return 1
        return 0
