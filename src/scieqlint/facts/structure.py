"""Structure facts lowered from Markdown/MyST/QMD-like sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scieqlint.diag.model import SourceSpan
from scieqlint.facts.base import FactBase
from scieqlint.facts.reference import TargetVisibility

FenceKind = Literal["generic", "math", "directive", "code-cell", "div"]
CodeCellSourceFormat = Literal["markdown", "notebook"]
StructureSyntaxKind = Literal[
    "atx-heading",
    "myst-directive",
    "myst-option",
    "myst-role",
    "code-cell-tags",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class HeadingFact(FactBase):
    level: int
    text: str
    raw: str | None = None
    marker_span: SourceSpan | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FenceFact(FactBase):
    opener: str
    info_string: str
    language: str | None
    kind: FenceKind
    is_closed: bool
    opener_span: SourceSpan
    body_span: SourceSpan | None


def _canonical_code_cell_label(value: str) -> str:
    """Normalize the label used by code-cell target identity."""

    value = value.strip()
    if value.startswith("#"):
        value = value[1:]
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class CodeCellFact(FactBase):
    language: str | None
    options: tuple[tuple[str, str], ...]
    label: str | None = None
    normalized_label: str | None
    label_span: SourceSpan | None = None
    language_span: SourceSpan | None = None
    source_format: CodeCellSourceFormat = "markdown"
    visibility: TargetVisibility = "visible"

    def __post_init__(self) -> None:
        if (self.label is None) != (self.normalized_label is None):
            raise ValueError("code-cell label and normalized label must both be present or absent")
        if self.label is None:
            return
        canonical_label = _canonical_code_cell_label(self.label)
        if not canonical_label or self.normalized_label != canonical_label:
            raise ValueError(
                "code-cell normalized label must be a non-empty canonical normalization of label"
            )

    def option_dict(self) -> dict[str, str]:
        return dict(self.options)


@dataclass(frozen=True, slots=True, kw_only=True)
class NotebookOutputFact(FactBase):
    cell_fact_id: str
    output_index: int
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class StructureSyntaxIssueFact(FactBase):
    kind: StructureSyntaxKind
    raw: str | None = None
