"""Configuration data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal

DimensionMode = Literal["auto", "on", "off"]
UnknownVariablePolicy = Literal["warn", "ignore"]


@dataclass(frozen=True, slots=True)
class DimVector:
    exponents: tuple[int, int, int, int, int, int, int]


@dataclass(frozen=True, slots=True)
class VarDimension:
    name: str
    dimension: DimVector


@dataclass(frozen=True, slots=True)
class SymbolAlias:
    canonical: str
    alias: str


@dataclass(frozen=True, slots=True)
class ScannerConfig:
    markdown: bool = True
    inline_math: bool = False
    math_fences: bool = True


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    root: PurePosixPath = PurePosixPath(".")
    order: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BaselineConfig:
    files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AlgebraConfig:
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ParserConfig:
    strict_unknowns: bool = False


@dataclass(frozen=True, slots=True)
class ReferencesConfig:
    enabled: bool = True
    missing_label_strict: bool = False


@dataclass(frozen=True, slots=True)
class DimensionConfig:
    mode: DimensionMode = "auto"
    unknown_variables: UnknownVariablePolicy = "warn"

    def is_active(self, *, has_vars: bool) -> bool:
        if self.mode == "off":
            return False
        if self.mode == "on":
            return True
        return has_vars


@dataclass(frozen=True, slots=True)
class SymbolsConfig:
    enabled: bool = False


@dataclass(frozen=True, slots=True)
class ChecksConfig:
    algebra: AlgebraConfig = field(default_factory=AlgebraConfig)
    references: ReferencesConfig = field(default_factory=ReferencesConfig)
    dimension: DimensionConfig = field(default_factory=DimensionConfig)
    symbols: SymbolsConfig = field(default_factory=SymbolsConfig)


@dataclass(frozen=True, slots=True)
class IgnoreConfig:
    files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReportConfig:
    show_suppressed: bool = False


@dataclass(frozen=True, slots=True)
class Config:
    """Config model for the first supported Markdown/MyST checks."""

    path: PurePosixPath | None = None
    project: ProjectConfig = field(default_factory=ProjectConfig)
    baseline: BaselineConfig = field(default_factory=BaselineConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    parser: ParserConfig = field(default_factory=ParserConfig)
    checks: ChecksConfig = field(default_factory=ChecksConfig)
    vars: tuple[VarDimension, ...] = ()
    aliases: tuple[SymbolAlias, ...] = ()
    ignore: IgnoreConfig = field(default_factory=IgnoreConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
