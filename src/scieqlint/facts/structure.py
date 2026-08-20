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
    slug_candidate: str
    explicit_anchor_ids: tuple[str, ...] = ()
    marker_span: SourceSpan | None = None
    text_span: SourceSpan | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SectionFact(FactBase):
    heading_fact_id: str
    parent_section_id: str | None
    depth: int
    ordinal_path: tuple[int, ...]
    starts_at: SourceSpan | None = None
    ends_before: SourceSpan | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FenceFact(FactBase):
    opener: str
    fence_char: str
    fence_length: int
    info_string: str
    language: str | None
    kind: FenceKind
    is_closed: bool
    opener_span: SourceSpan
    closer_span: SourceSpan | None
    body_span: SourceSpan | None


@dataclass(frozen=True, slots=True, kw_only=True)
class DirectiveFact(FactBase):
    name: str
    argument: str | None
    options: tuple[tuple[str, str], ...]
    fence_fact_id: str
    known: bool | None = None
    parse_error: str | None = None

    def option_dict(self) -> dict[str, str]:
        return dict(self.options)


@dataclass(frozen=True, slots=True, kw_only=True)
class CodeCellFact(FactBase):
    fence_fact_id: str
    directive_fact_id: str | None
    language: str | None
    engine: str | None
    options: tuple[tuple[str, str], ...]
    label: str | None = None
    normalized_label: str | None = None
    label_span: SourceSpan | None = None
    language_span: SourceSpan | None = None
    source_format: CodeCellSourceFormat = "markdown"
    visibility: TargetVisibility = "visible"
    tags: tuple[str, ...] = ()
    output_target_labels: tuple[str, ...] = ()

    def option_dict(self) -> dict[str, str]:
        return dict(self.options)


@dataclass(frozen=True, slots=True, kw_only=True)
class NotebookOutputFact(FactBase):
    cell_fact_id: str
    cell_index: int
    output_index: int
    output_type: str
    mime_types: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class StructureSyntaxIssueFact(FactBase):
    kind: StructureSyntaxKind
    reason: str
