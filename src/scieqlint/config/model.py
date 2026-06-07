"""Configuration data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath


@dataclass(frozen=True, slots=True)
class ScannerConfig:
    markdown: bool = True
    inline_math: bool = False
    math_fences: bool = True


@dataclass(frozen=True, slots=True)
class AlgebraConfig:
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ReferencesConfig:
    enabled: bool = True
    missing_label_strict: bool = False


@dataclass(frozen=True, slots=True)
class ChecksConfig:
    algebra: AlgebraConfig = field(default_factory=AlgebraConfig)
    references: ReferencesConfig = field(default_factory=ReferencesConfig)


@dataclass(frozen=True, slots=True)
class Config:
    """Config model for the first supported Markdown/MyST checks."""

    path: PurePosixPath | None = None
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    checks: ChecksConfig = field(default_factory=ChecksConfig)
