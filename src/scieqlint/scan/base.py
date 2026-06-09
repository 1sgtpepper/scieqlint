"""Scanner contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from scieqlint.config.model import Config
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.io.source import SourceDocument


class MathContainer(Enum):
    MARKDOWN_DISPLAY = "markdown_display"
    MARKDOWN_FENCE = "markdown_fence"
    MARKDOWN_INLINE = "markdown_inline"
    LATEX_DISPLAY = "latex_display"
    LATEX_EQUATION = "latex_equation"
    LATEX_ALIGN = "latex_align"


class LabelSource(Enum):
    MARKDOWN_ANCHOR = "markdown_anchor"
    MYST_DOLLAR_LABEL = "myst_dollar_label"
    MYST_DIRECTIVE_LABEL = "myst_directive_label"
    TEX_LABEL_IN_MARKDOWN_MATH = "tex_label_in_markdown_math"
    LATEX_LABEL = "latex_label"


class ReferenceSource(Enum):
    MARKDOWN_ANCHOR = "markdown_anchor"
    MYST_EQ_ROLE = "myst_eq_role"
    MYST_NUMREF_ROLE = "myst_numref_role"
    LATEX_REF = "latex_ref"
    LATEX_EQREF = "latex_eqref"


class SymbolDirectiveSource(Enum):
    MARKDOWN_COMMENT = "markdown_comment"
    LATEX_COMMENT = "latex_comment"


@dataclass(frozen=True, slots=True)
class MathBlock:
    text: str
    span: SourceSpan
    block_id: str
    container: MathContainer


@dataclass(frozen=True, slots=True)
class EquationLabel:
    label: str
    span: SourceSpan
    block_id: str | None
    source: LabelSource


@dataclass(frozen=True, slots=True)
class EquationReference:
    target: str
    span: SourceSpan
    raw: str
    source: ReferenceSource


@dataclass(frozen=True, slots=True)
class SymbolDirective:
    symbol: str
    description: str
    dimension: str | None
    span: SourceSpan
    raw: str
    source: SymbolDirectiveSource


@dataclass(frozen=True, slots=True)
class ScanResult:
    blocks: tuple[MathBlock, ...]
    labels: tuple[EquationLabel, ...] = ()
    references: tuple[EquationReference, ...] = ()
    symbol_directives: tuple[SymbolDirective, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


class Scanner(Protocol):
    def scan(self, document: SourceDocument, config: Config) -> ScanResult: ...
