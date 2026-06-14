"""Base contracts for immutable architecture facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scieqlint.diag.model import SourceSpan
from scieqlint.source.maps import Origin

Confidence = Literal["source", "generated", "inferred", "external"]


@dataclass(frozen=True, slots=True, kw_only=True)
class FactBase:
    """Common fact fields.

    Fact subclasses should be cheap data records, not behavior-heavy AST nodes.
    The FactSnapshot owns indexing; QueryViews own interpretation; engines own
    diagnostics.
    """

    fact_id: str
    document_id: str
    span: SourceSpan | None
    raw: str | None = None
    origin: Origin | None = None
    confidence: Confidence = "source"
